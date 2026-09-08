param(
    [ValidateSet(
        "start", "stop", "status", "sync-data", "refresh-news", "enhance-news", "rebuild-serving",
        "build-selection", "rebuild-selection", "selection-status", "selection-rollback"
    )]
    [string]$Command = "start",
    [string]$SelectionGeneration,
    [string]$NewsBudgetPath,
    [string]$NewsRunId,
    [ValidateRange(1, 100)] [int]$NewsBudgetLimit = 16,
    [ValidateRange(1, 40)] [int]$NewsItemLimit = 18,
    [switch]$InitializeNewsBudget
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FrontendRoot = Join-Path $RepoRoot "frontend"
$BackendRoot = Join-Path $RepoRoot "backend"
$ControlRoot = Join-Path $env:LOCALAPPDATA "TopicEyeRardarLLMControl"
$RuntimeRoot = Join-Path $env:LOCALAPPDATA "RardarLocalProductMVP"
$MirrorRoot = Join-Path $env:LOCALAPPDATA "TopicEye\rardar-intelligence"
$StatePath = Join-Path $RuntimeRoot "runtime.json"
$PgRoot = Join-Path $ControlRoot "pgsql"
$PgData = Join-Path $ControlRoot "pgdata"
$PgCtl = Join-Path $PgRoot "bin\pg_ctl.exe"
$PgReady = Join-Path $PgRoot "bin\pg_isready.exe"
$Psql = Join-Path $PgRoot "bin\psql.exe"
$Python = Join-Path $ControlRoot "venv-20260826\Scripts\python.exe"
$PgPort = if ($env:RARDAR_LOCAL_PG_PORT) { [int]$env:RARDAR_LOCAL_PG_PORT } else { 55433 }
$BundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$Node = if (Test-Path -LiteralPath $BundledNode) { $BundledNode } else { (Get-Command node.exe).Source }
$NpmCli = Join-Path (Split-Path (Get-Command npm.cmd).Source) "node_modules\npm\bin\npm-cli.js"

function Read-State {
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return $null }
    return Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
}

function Test-Process([object]$ProcessId) {
    if (-not $ProcessId) { return $false }
    return $null -ne (Get-Process -Id ([int]$ProcessId) -ErrorAction SilentlyContinue)
}

function Test-Http([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-LoopbackListenerPid([int]$Port) {
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne "127.0.0.1") {
        throw "Expected exactly one loopback listener on port $Port."
    }
    return [int]$listeners[0].OwningProcess
}

function Test-ProcessDescendsFrom([int]$ProcessId, [int]$AncestorId) {
    $current = $ProcessId
    foreach ($depth in 0..16) {
        if ($current -eq $AncestorId) { return $true }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $current" -ErrorAction SilentlyContinue
        if (-not $process -or -not $process.ParentProcessId -or $process.ParentProcessId -eq $current) {
            return $false
        }
        $current = [int]$process.ParentProcessId
    }
    return $false
}

function Resolve-LocalSelectionSource(
    [string]$DataRoot = $MirrorRoot,
    [string]$PythonExecutable = $Python,
    [string]$ApplicationRoot = $BackendRoot,
    [scriptblock]$NormalValidator = $null
) {
    $store = Join-Path $DataRoot "discover-worth-seeing"
    $pointerPath = Join-Path $store "current.json"

    foreach ($directory in @($DataRoot, $store)) {
        if (-not (Test-Path -LiteralPath $directory)) { continue }
        $item = Get-Item -LiteralPath $directory -Force
        if (
            -not $item.PSIsContainer `
            -or (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
        ) {
            throw "Rardar Selection data path is unsafe; local source selection stopped."
        }
    }

    if (-not (Test-Path -LiteralPath $pointerPath)) {
        return [pscustomobject]@{
            source = "shadow"
            localShadowReview = $true
            selectionGenerationId = $null
        }
    }
    if (-not (Test-Path -LiteralPath $pointerPath -PathType Leaf)) {
        throw "Rardar Selection current pointer is not a regular file."
    }

    $before = Get-Item -LiteralPath $pointerPath -Force
    if (
        $before.PSIsContainer `
        -or (($before.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) `
        -or $before.Length -le 0 `
        -or $before.Length -gt (64 * 1024)
    ) {
        throw "Rardar Selection current pointer is unsafe."
    }
    try {
        $raw = [System.IO.File]::ReadAllText($pointerPath, [System.Text.Encoding]::UTF8)
    } catch {
        throw "Rardar Selection current pointer could not be read safely."
    }
    $after = Get-Item -LiteralPath $pointerPath -Force
    if (
        $after.PSIsContainer `
        -or (($after.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) `
        -or $after.Length -ne $before.Length `
        -or $after.LastWriteTimeUtc.Ticks -ne $before.LastWriteTimeUtc.Ticks
    ) {
        throw "Rardar Selection current pointer changed during validation."
    }

    try {
        # Preserve the original RFC3339 token.  PowerShell's default date
        # coercion discards the exact offset spelling before we can verify it.
        $pointer = $raw | ConvertFrom-Json -DateKind String
    } catch {
        throw "Rardar Selection current pointer is invalid JSON."
    }
    if ($pointer -isnot [pscustomobject]) {
        throw "Rardar Selection current pointer must be a JSON object."
    }

    $properties = @($pointer.PSObject.Properties.Name)
    $required = @(
        "schemaVersion", "selectionGenerationId", "sourceObservationSetId",
        "manifestSha256", "activatedAt"
    )
    $allowed = @($required + @("activationState", "activationPolicyVersion"))
    if (
        @($required | Where-Object { $_ -cnotin $properties }).Count -ne 0 `
        -or @($properties | Where-Object { $_ -cnotin $allowed }).Count -ne 0
    ) {
        throw "Rardar Selection current pointer has an untrusted structure."
    }
    if (
        ($pointer.schemaVersion -isnot [int] -and $pointer.schemaVersion -isnot [long]) `
        -or [int64]$pointer.schemaVersion -ne 1 `
        -or $pointer.selectionGenerationId -isnot [string] `
        -or $pointer.selectionGenerationId -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{1,190}$' `
        -or $pointer.sourceObservationSetId -isnot [string] `
        -or $pointer.sourceObservationSetId.Length -lt 2 `
        -or $pointer.sourceObservationSetId.Length -gt 190 `
        -or $pointer.manifestSha256 -isnot [string] `
        -or $pointer.manifestSha256 -cnotmatch '^[a-f0-9]{64}$' `
        -or $pointer.activatedAt -isnot [string] `
        -or $pointer.activatedAt -cnotmatch '(?:Z|[+-][0-9]{2}:[0-9]{2})$'
    ) {
        throw "Rardar Selection current pointer has invalid identity metadata."
    }
    $activatedAt = [datetimeoffset]::MinValue
    if (-not [datetimeoffset]::TryParse(
        $pointer.activatedAt,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind,
        [ref]$activatedAt
    )) {
        throw "Rardar Selection current pointer has an invalid activation time."
    }

    $hasActivationState = $properties -ccontains "activationState"
    $hasActivationPolicy = $properties -ccontains "activationPolicyVersion"
    if (-not $hasActivationState -and -not $hasActivationPolicy) {
        # An otherwise well-formed v1 pointer predates audited activation.  It
        # remains retained, but the local product keeps showing the historical
        # Shadow until a v2 ready/empty pointer is atomically installed.
        return [pscustomobject]@{
            source = "shadow"
            localShadowReview = $true
            selectionGenerationId = $null
        }
    }
    if (-not $hasActivationState -or -not $hasActivationPolicy) {
        throw "Rardar Selection activation metadata is incomplete."
    }
    if (
        $pointer.activationPolicyVersion -cne "worth-seeing-activation-v2" `
        -or $pointer.activationState -cnotin @("ready", "empty")
    ) {
        throw "Rardar Selection current pointer is not eligible for normal serving."
    }

    if ($NormalValidator) {
        $validatedGeneration = & $NormalValidator $DataRoot $pointer.selectionGenerationId
    } else {
        if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
            throw "TopicEye Python is unavailable for audited Selection validation."
        }
        $validationProgram = @'
import sys
from app.integrations.rardar.selection_serving import SelectionServingLoader

snapshot, _etag = SelectionServingLoader(sys.argv[1]).load_with_etag()
if snapshot.selectionGenerationId != sys.argv[2]:
    raise RuntimeError("selection generation changed during validation")
print(snapshot.selectionGenerationId)
'@
        $savedPythonPath = $env:PYTHONPATH
        $savedDatabaseUrl = $env:DATABASE_URL
        $env:PYTHONPATH = $ApplicationRoot
        if (-not $env:DATABASE_URL) {
            $env:DATABASE_URL = "postgresql+asyncpg://selection-source@127.0.0.1:1/selection-source"
        }
        try {
            $validationOutput = @(& $PythonExecutable -c $validationProgram $DataRoot $pointer.selectionGenerationId 2>$null)
            $validationExitCode = $LASTEXITCODE
        } finally {
            $env:PYTHONPATH = $savedPythonPath
            $env:DATABASE_URL = $savedDatabaseUrl
        }
        if ($validationExitCode -ne 0) {
            throw "Rardar Selection current generation failed audited validation."
        }
        $validatedGeneration = @($validationOutput | Where-Object { $_ })[-1]
    }
    if (-not $validatedGeneration -or $validatedGeneration.Trim() -cne $pointer.selectionGenerationId) {
        throw "Rardar Selection validation returned a mismatched generation."
    }

    return [pscustomobject]@{
        source = "normal"
        localShadowReview = $false
        selectionGenerationId = $pointer.selectionGenerationId
    }
}

function Assert-RecordedRuntime(
    [object]$State,
    [string]$Head,
    [string]$DataMode,
    [string]$SelectionSource
) {
    $expectedShadowReview = $SelectionSource -eq "shadow"
    if (
        -not $State `
        -or $State.repository -ne $RepoRoot `
        -or $State.head -ne $Head `
        -or $State.frontendMode -ne "production" `
        -or [bool]$State.localShadowReview -ne $expectedShadowReview `
        -or $State.selectionSource -ne $SelectionSource `
        -or $State.dataMode -ne $DataMode `
        -or $State.dataMirror -ne $MirrorRoot `
        -or -not (Test-Process $State.backendPid) `
        -or -not (Test-Process $State.frontendPid)
    ) {
        throw "Recorded Rardar Runtime does not match the requested source and product mode."
    }

    $backend = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$State.backendPid)"
    $frontend = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$State.frontendPid)"
    if (
        -not $backend `
        -or $backend.Name -notmatch "^python(w)?\.exe$" `
        -or -not $backend.CommandLine `
        -or $backend.CommandLine.IndexOf($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0 `
        -or $backend.CommandLine -notmatch "(?i)\buvicorn\b" `
        -or $backend.CommandLine -notmatch "(?i)--port\s+8102" `
        -or -not $frontend `
        -or $frontend.Name -ne "node.exe" `
        -or -not $frontend.CommandLine `
        -or $frontend.CommandLine.IndexOf($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0 `
        -or $frontend.CommandLine -notmatch "(?i)next(?:\.js)?[\\/]dist[\\/]bin[\\/]next" `
        -or $frontend.CommandLine -notmatch "(?i)\sstart\s" `
        -or $frontend.CommandLine -notmatch "(?i)--port\s+3000"
    ) {
        throw "Recorded Rardar Runtime process identity does not match production startup."
    }

    $backendListenerPid = Get-LoopbackListenerPid 8102
    $frontendListenerPid = Get-LoopbackListenerPid 3000
    if (
        $backendListenerPid -ne [int]$State.backendListenerPid `
        -or $frontendListenerPid -ne [int]$State.frontendListenerPid `
        -or -not (Test-ProcessDescendsFrom $backendListenerPid ([int]$State.backendPid)) `
        -or -not (Test-ProcessDescendsFrom $frontendListenerPid ([int]$State.frontendPid)) `
        -or -not (Test-Http "http://127.0.0.1:8102/health/live") `
        -or -not (Test-Http "http://127.0.0.1:3000/api/health")
    ) {
        throw "Recorded Rardar Runtime listener or health identity does not match."
    }

    $buildIdPath = Join-Path $FrontendRoot ".next\BUILD_ID"
    if (
        -not (Test-Path -LiteralPath $buildIdPath -PathType Leaf) `
        -or (Get-Content -LiteralPath $buildIdPath -Raw).Trim() -ne $State.frontendBuildId
    ) {
        throw "Recorded Rardar Runtime build identity does not match the installed production build."
    }
}

function Write-StateAtomically([object]$State) {
    $temporary = Join-Path $RuntimeRoot ("runtime.json.{0}.{1}.tmp" -f $PID, [Guid]::NewGuid().ToString("N"))
    $backup = Join-Path $RuntimeRoot ("runtime.json.{0}.{1}.bak" -f $PID, [Guid]::NewGuid().ToString("N"))
    try {
        $json = $State | ConvertTo-Json -Depth 8
        [System.IO.File]::WriteAllText($temporary, $json, [System.Text.UTF8Encoding]::new($false))
        $parsed = Get-Content -LiteralPath $temporary -Raw | ConvertFrom-Json
        if (
            $parsed.repository -ne $State.repository `
            -or $parsed.head -ne $State.head `
            -or [int]$parsed.backendPid -ne [int]$State.backendPid `
            -or [int]$parsed.frontendPid -ne [int]$State.frontendPid
        ) {
            throw "Runtime state verification failed before publication."
        }
        if (Test-Path -LiteralPath $StatePath -PathType Leaf) {
            [System.IO.File]::Replace($temporary, $StatePath, $backup)
        } else {
            [System.IO.File]::Move($temporary, $StatePath)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
        if (Test-Path -LiteralPath $backup) {
            Remove-Item -LiteralPath $backup -Force
        }
    }
}

function Show-Status {
    $state = Read-State
    $postgresHealthy = (& $PgReady -h 127.0.0.1 -p $PgPort 2>$null) -match "accepting connections"
    [pscustomobject]@{
        Repository = $RepoRoot
        PostgreSQL = if ($postgresHealthy) { "healthy" } else { "stopped" }
        Backend = if ($state -and (Test-Process $state.backendPid) -and (Test-Http "http://127.0.0.1:8102/health/live")) { "healthy" } else { "stopped" }
        Frontend = if ($state -and (Test-Process $state.frontendPid) -and (Test-Http "http://127.0.0.1:3000/api/health")) { "healthy" } else { "stopped" }
        FrontendMode = if ($state -and $state.frontendMode) { $state.frontendMode } else { "unknown" }
        Head = if ($state -and $state.head) { $state.head } else { "unknown" }
        DataMode = if ($state -and $state.dataMode) { $state.dataMode } elseif ($env:RARDAR_DATA_MODE) { $env:RARDAR_DATA_MODE } else { "real" }
        SelectionSource = if ($state -and $state.selectionSource) { $state.selectionSource } elseif ($state -and $state.localShadowReview) { "shadow" } else { "unknown" }
        DataMirror = $MirrorRoot
        DataSynced = if (Test-Path -LiteralPath (Join-Path $MirrorRoot "serving\current.json") -PathType Leaf) { "yes" } else { "no; run rebuild-serving" }
        Selection = if (Test-Path -LiteralPath (Join-Path $MirrorRoot "discover-worth-seeing\current.json") -PathType Leaf) { "built" } else { "not built; run build-selection" }
        Product = "http://127.0.0.1:3000/"
        Login = "http://127.0.0.1:3000/login"
        Admin = "http://127.0.0.1:3000/admin"
        Models = "http://127.0.0.1:3000/admin/model-eval"
    } | Format-List
}

function Stop-AppProcess(
    [object]$ProcessId,
    [string]$ExpectedName,
    [int]$ExpectedPort = 0,
    [object]$ExpectedListenerPid = $null
) {
    if (Test-Process $ProcessId) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$ProcessId)"
        if (
            -not $process `
            -or $process.Name -notmatch $ExpectedName `
            -or -not $process.CommandLine `
            -or $process.CommandLine.IndexOf($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0
        ) {
            throw "Refusing to stop an unexpected process recorded in local runtime state."
        }
        & taskkill.exe /PID ([int]$ProcessId) /T /F | Out-Null
    }

    $deadline = (Get-Date).AddSeconds(8)
    do {
        $parentAlive = Test-Process $ProcessId
        $listenerAlive = $ExpectedListenerPid -and (Test-Process $ExpectedListenerPid)
        if (-not $parentAlive -and -not $listenerAlive) { break }
        Start-Sleep -Milliseconds 200
    } while ((Get-Date) -lt $deadline)

    $portListeners = if ($ExpectedPort) {
        @(Get-NetTCPConnection -LocalPort $ExpectedPort -State Listen -ErrorAction SilentlyContinue)
    } else {
        @()
    }
    if ((Test-Process $ProcessId) -or ($ExpectedListenerPid -and (Test-Process $ExpectedListenerPid)) -or $portListeners) {
        throw "Rardar process cleanup could not be verified; runtime state was preserved."
    }
}

function Stop-Rardar {
    $state = Read-State
    if ($state) {
        if (-not $state.repository -or $state.repository -ne $RepoRoot) {
            throw "Refusing to use local runtime state owned by another repository."
        }
        Stop-AppProcess $state.frontendPid "^(node|cmd)\.exe$" 3000 $state.frontendListenerPid
        Stop-AppProcess $state.backendPid "^python(w)?\.exe$" 8102 $state.backendListenerPid
        Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Rardar frontend/backend stopped. Existing PostgreSQL data was preserved."
    Show-Status
}

function Start-Postgres {
    foreach ($required in @($PgCtl, $PgReady, $Psql, $PgData, $Python, $Node, $NpmCli)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Existing TopicEye local runtime is incomplete: $required"
        }
    }
    $listeners = @(Get-NetTCPConnection -LocalPort $PgPort -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        if ($listeners.Count -ne 1 -or $listeners[0].LocalAddress -ne "127.0.0.1") {
            throw "Existing PostgreSQL listener identity is unclear."
        }
        $postgres = Get-CimInstance Win32_Process -Filter "ProcessId = $($listeners[0].OwningProcess)"
        $expectedExecutable = Join-Path $PgRoot "bin\postgres.exe"
        if (
            -not $postgres `
            -or $postgres.ExecutablePath -ine $expectedExecutable `
            -or -not $postgres.CommandLine `
            -or $postgres.CommandLine.Replace("/", "\").IndexOf($PgData, [StringComparison]::OrdinalIgnoreCase) -lt 0
        ) {
            throw "Port $PgPort is not owned by the existing TopicEye PostgreSQL runtime."
        }
        if (-not ((& $PgReady -h 127.0.0.1 -p $PgPort 2>$null) -match "accepting connections")) {
            throw "Existing TopicEye PostgreSQL listener is not healthy."
        }
        return
    }

    $pidPath = Join-Path $PgData "postmaster.pid"
    if (Test-Path -LiteralPath $pidPath) {
        $recordedPidText = (Get-Content -LiteralPath $pidPath -TotalCount 1).Trim()
        $recordedPid = 0
        if (-not [int]::TryParse($recordedPidText, [ref]$recordedPid) -or $recordedPid -le 0) {
            throw "Existing PostgreSQL PID record is invalid; it was left unchanged."
        }
        if (Test-Process $recordedPid) {
            throw "Existing PostgreSQL PID is alive without the expected listener; refusing to start a second server."
        }
    }
    $pgLog = Join-Path $ControlRoot "postgres.log"
    & $PgCtl start -D $PgData -l $pgLog -o "-p $PgPort -h 127.0.0.1" -w -t 60
    if ($LASTEXITCODE -ne 0 -or -not ((& $PgReady -h 127.0.0.1 -p $PgPort 2>$null) -match "accepting connections")) {
        throw "Existing TopicEye PostgreSQL could not be started; see $pgLog"
    }
    $null = Get-LoopbackListenerPid $PgPort
}

function Resolve-Database {
    if ($env:RARDAR_LOCAL_DATABASE) { return $env:RARDAR_LOCAL_DATABASE }
    $databases = & $Psql -h 127.0.0.1 -p $PgPort -U $script:DatabaseUser -d postgres -At -c "select datname from pg_database where datistemplate = false and datname <> 'postgres' order by datname"
    $matches = @()
    foreach ($database in $databases) {
        if (-not $database) { continue }
        $hasModels = & $Psql -h 127.0.0.1 -p $PgPort -U $script:DatabaseUser -d $database -At -c "select case when to_regclass('public.llm_models') is null then 0 else 1 end"
        if ($hasModels -ne "1") { continue }
        $rardarModels = & $Psql -h 127.0.0.1 -p $PgPort -U $script:DatabaseUser -d $database -At -c "select count(*) from llm_models where enabled is true and routing_group = 'rardar'"
        if ([int]$rardarModels -gt 0) { $matches += $database }
    }
    if ($matches.Count -ne 1) {
        throw "Could not uniquely identify the existing database with an enabled rardar route. Set RARDAR_LOCAL_DATABASE explicitly; no database was created or changed."
    }
    return $matches[0]
}

function Resolve-DatabaseUser {
    $candidates = if ($env:RARDAR_LOCAL_DATABASE_USER) {
        @($env:RARDAR_LOCAL_DATABASE_USER)
    } else {
        @("topiceye", "postgres", $env:USERNAME) | Select-Object -Unique
    }
    foreach ($candidate in $candidates) {
        if (-not $candidate) { continue }
        $resolved = & $Psql -h 127.0.0.1 -p $PgPort -U $candidate -d postgres -At -c "select current_user" 2>$null
        if ($LASTEXITCODE -eq 0 -and $resolved) { return $resolved.Trim() }
    }
    throw "Could not identify the existing TopicEye PostgreSQL role. Set RARDAR_LOCAL_DATABASE_USER; no role was created."
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-Http $Url) { return }
        Start-Sleep -Milliseconds 750
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url"
}

function Start-Rardar {
    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    $head = (& git -C $RepoRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $head) {
        throw "Could not identify the Runtime source revision."
    }
    $dirty = & git -C $RepoRoot status --short --untracked-files=all
    if ($LASTEXITCODE -ne 0 -or $dirty) {
        throw "Runtime worktree must be clean before startup."
    }
    $dataMode = if ($env:RARDAR_DATA_MODE) { $env:RARDAR_DATA_MODE.Trim().ToLowerInvariant() } else { "real" }
    if ($dataMode -notin @("real", "demo")) {
        throw 'RARDAR_DATA_MODE must be "real" or "demo".'
    }
    $selection = Resolve-LocalSelectionSource
    $selectionSource = $selection.source
    $localShadowReview = [bool]$selection.localShadowReview

    $existing = Read-State
    if ($existing -and ((Test-Process $existing.backendPid) -or (Test-Process $existing.frontendPid))) {
        Assert-RecordedRuntime $existing $head $dataMode $selectionSource
        Show-Status
        return
    }
    foreach ($port in @(3000, 8102)) {
        if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
            throw "Port $port is already occupied. Stop the existing local process before starting Rardar."
        }
    }

    Start-Postgres
    $script:DatabaseUser = Resolve-DatabaseUser
    $database = Resolve-Database
    $encodedUser = [Uri]::EscapeDataString($script:DatabaseUser)
    $encodedDatabase = [Uri]::EscapeDataString($database)
    $databaseUrl = "postgresql+asyncpg://${encodedUser}@127.0.0.1:${PgPort}/${encodedDatabase}"
    if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot "node_modules"))) {
        Push-Location $FrontendRoot
        try { & $Node $NpmCli ci } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    }

    $savedEnvironment = @{}
    $backendEnvironment = @{
        DATABASE_URL = $databaseUrl
        APP_ENV = "development"
        RARDAR_PRODUCT_MODE = "true"
        RARDAR_DATA_MODE = $dataMode
        RARDAR_DEMO_DATA_ENABLED = "false"
        RARDAR_LOCAL_SHADOW_REVIEW = if ($localShadowReview) { "true" } else { "false" }
        RARDAR_INTELLIGENCE_DATA_DIR = $MirrorRoot
        CORS_ORIGINS = "http://127.0.0.1:3000"
        SCHEDULER_ENABLED = "false"
        CACHE_WARMUP_ENABLED = "false"
        DUCKDB_STARTUP_INIT_ENABLED = "false"
        STARTUP_SEED_ENABLED = "false"
        ADMIN_SEED_ENABLED = "false"
        RARDAR_LLM_RUN_ID = $null
        RARDAR_LLM_BUDGET_PATH = $null
        RARDAR_LLM_BUDGET_LIMIT = $null
        PYTHONUTF8 = "1"
        PYTHONIOENCODING = "utf-8"
    }
    foreach ($name in $backendEnvironment.Keys) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $backendEnvironment[$name], "Process")
    }
    $statePublished = $false
    try {
        $backend = Start-Process -FilePath $Python -ArgumentList @("-m", "uvicorn", "app.main:app", "--app-dir", $BackendRoot, "--host", "127.0.0.1", "--port", "8102") -WorkingDirectory $BackendRoot -RedirectStandardOutput (Join-Path $RuntimeRoot "backend.out.log") -RedirectStandardError (Join-Path $RuntimeRoot "backend.err.log") -WindowStyle Hidden -PassThru
    } finally {
        foreach ($name in $backendEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
        }
    }
    try {
        # /health/live proves both the HTTP process and PostgreSQL connection.
        # The deeper /health/ready may probe optional DuckDB state and is not a
        # local product startup gate.
        Wait-Http "http://127.0.0.1:8102/health/live" 120
        $savedFrontendEnvironment = @{}
        $frontendEnvironment = @{
            NODE_ENV = "production"
            RARDAR_PRODUCT_MODE = "true"
            BACKEND_API_URL = "http://127.0.0.1:8102"
            NEXT_TELEMETRY_DISABLED = "1"
        }
        foreach ($name in $frontendEnvironment.Keys) {
            $savedFrontendEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
            [Environment]::SetEnvironmentVariable($name, $frontendEnvironment[$name], "Process")
        }
        try {
            $next = Join-Path $FrontendRoot "node_modules\next\dist\bin\next"
            Push-Location $FrontendRoot
            try {
                & $Node $next build --webpack
                $buildExitCode = $LASTEXITCODE
            } finally {
                Pop-Location
            }
            if ($buildExitCode -ne 0) { throw "Rardar production frontend build failed." }
            if (& git -C $RepoRoot status --short --untracked-files=all) {
                throw "Runtime source changed while building the frontend."
            }
            $routes = Get-Content -LiteralPath (Join-Path $FrontendRoot ".next\routes-manifest.json") -Raw | ConvertFrom-Json
            $apiRewrite = @($routes.rewrites.afterFiles | Where-Object { $_.source -eq "/api/:path*" })
            if ($apiRewrite.Count -ne 1 -or $apiRewrite[0].destination -ne "http://127.0.0.1:8102/api/:path*") {
                throw "Rardar production frontend build has an unexpected backend binding."
            }
            $frontendBuildId = (Get-Content -LiteralPath (Join-Path $FrontendRoot ".next\BUILD_ID") -Raw).Trim()
            $frontend = Start-Process -FilePath $Node -ArgumentList @($next, "start", "--hostname", "127.0.0.1", "--port", "3000") -WorkingDirectory $FrontendRoot -RedirectStandardOutput (Join-Path $RuntimeRoot "frontend.out.log") -RedirectStandardError (Join-Path $RuntimeRoot "frontend.err.log") -WindowStyle Hidden -PassThru
        } finally {
            foreach ($name in $frontendEnvironment.Keys) {
                [Environment]::SetEnvironmentVariable($name, $savedFrontendEnvironment[$name], "Process")
            }
        }
        Wait-Http "http://127.0.0.1:3000/api/health" 120
        $backendListenerPid = Get-LoopbackListenerPid 8102
        $frontendListenerPid = Get-LoopbackListenerPid 3000

        $runtimeState = [pscustomobject]@{
            schemaVersion = 3
            repository = $RepoRoot
            startedAt = (Get-Date).ToUniversalTime().ToString("o")
            backendPid = $backend.Id
            backendListenerPid = $backendListenerPid
            frontendPid = $frontend.Id
            frontendListenerPid = $frontendListenerPid
            postgresPort = $PgPort
            database = $database
            dataMode = $dataMode
            dataMirror = $MirrorRoot
            head = $head
            frontendMode = "production"
            frontendBuildId = $frontendBuildId
            localShadowReview = $localShadowReview
            selectionSource = $selectionSource
        }
        Write-StateAtomically $runtimeState
        $statePublished = $true
        Assert-RecordedRuntime (Read-State) $head $dataMode $selectionSource
        Show-Status
    } catch {
        $startupError = $_
        $cleanupErrors = @()
        try {
            if ($frontend) {
                Stop-AppProcess $frontend.Id "^node\.exe$" 3000 $frontendListenerPid
            }
        } catch {
            $cleanupErrors += $_.Exception.Message
        }
        try {
            if ($backend) {
                Stop-AppProcess $backend.Id "^python(w)?\.exe$" 8102 $backendListenerPid
            }
        } catch {
            $cleanupErrors += $_.Exception.Message
        }

        if ($statePublished) {
            $published = $null
            try { $published = Read-State } catch { $published = $null }
            if (
                $cleanupErrors.Count -eq 0 `
                -and $published `
                -and [int]$published.backendPid -eq [int]$backend.Id `
                -and [int]$published.frontendPid -eq [int]$frontend.Id
            ) {
                Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
            } elseif ($cleanupErrors.Count -eq 0) {
                $cleanupErrors += "Published Runtime state could not be matched for safe removal."
            }
        }
        if ($cleanupErrors.Count -gt 0) {
            throw "Rardar startup failed and cleanup was not fully verified; runtime state was preserved. $($cleanupErrors -join ' ')"
        }
        throw $startupError
    }
}

function Sync-RardarData {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Existing TopicEye Python runtime is unavailable: $Python"
    }
    Start-Postgres
    $script:DatabaseUser = Resolve-DatabaseUser
    $database = Resolve-Database
    $encodedUser = [Uri]::EscapeDataString($script:DatabaseUser)
    $encodedDatabase = [Uri]::EscapeDataString($database)
    $databaseUrl = "postgresql+asyncpg://${encodedUser}@127.0.0.1:${PgPort}/${encodedDatabase}"
    $sourceHost = if ($env:RARDAR_SYNC_SOURCE_HOST) { $env:RARDAR_SYNC_SOURCE_HOST } else { "rardar-prod" }
    $remoteRoot = if ($env:RARDAR_SYNC_REMOTE_ROOT) { $env:RARDAR_SYNC_REMOTE_ROOT } else { "/var/lib/rardar/data" }
    $savedPythonPath = $env:PYTHONPATH
    $savedDatabaseUrl = $env:DATABASE_URL
    $env:PYTHONPATH = $BackendRoot
    $env:DATABASE_URL = $databaseUrl
    Push-Location $BackendRoot
    try {
        & $Python -m scripts.sync_rardar_intelligence --target $MirrorRoot --host $sourceHost --remote-root $remoteRoot
        if ($LASTEXITCODE -ne 0) { throw "Rardar read-only data sync failed." }
        $selectionSourceArguments = @(
            "-m", "scripts.sync_rardar_selection_source",
            "--target", $MirrorRoot,
            "--host", $sourceHost,
            "--remote-root", $remoteRoot
        )
        if ($env:RARDAR_SELECTION_SYNC_SOURCE_DIR) {
            $selectionSourceArguments += @("--source-dir", $env:RARDAR_SELECTION_SYNC_SOURCE_DIR)
        }
        & $Python @selectionSourceArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Rardar Selection fact sync failed; any previously active Selection source pointer was preserved."
        }
        # Production Discover is intentionally optional.  Keep the legacy
        # momentum mirror only as an explicitly requested Shadow comparator;
        # it is never a prerequisite for worth-seeing Selection.
        if ($env:RARDAR_DISCOVER_SYNC_ENABLED -eq "1") {
            $discoverArguments = @(
                "-m", "scripts.sync_rardar_discover",
                "--target", $MirrorRoot,
                "--host", $sourceHost,
                "--remote-root", $remoteRoot
            )
            if ($env:RARDAR_DISCOVER_SYNC_SOURCE_DIR) {
                $discoverArguments += @("--source-dir", $env:RARDAR_DISCOVER_SYNC_SOURCE_DIR)
            }
            & $Python @discoverArguments
            if ($LASTEXITCODE -ne 0) {
                throw "Optional legacy Rardar Discover sync failed; existing mirrors were preserved."
            }
        }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $savedPythonPath
        $env:DATABASE_URL = $savedDatabaseUrl
    }
}

function Rebuild-RardarServing {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Existing TopicEye Python runtime is unavailable: $Python"
    }
    Start-Postgres
    $script:DatabaseUser = Resolve-DatabaseUser
    $database = Resolve-Database
    $encodedUser = [Uri]::EscapeDataString($script:DatabaseUser)
    $encodedDatabase = [Uri]::EscapeDataString($database)
    $databaseUrl = "postgresql+asyncpg://${encodedUser}@127.0.0.1:${PgPort}/${encodedDatabase}"
    $savedPythonPath = $env:PYTHONPATH
    $savedDatabaseUrl = $env:DATABASE_URL
    $env:PYTHONPATH = $BackendRoot
    $env:DATABASE_URL = $databaseUrl
    Push-Location $BackendRoot
    try {
        & $Python -m scripts.rebuild_rardar_serving --target $MirrorRoot
        if ($LASTEXITCODE -ne 0) { throw "Rardar serving projection rebuild failed." }
        $discoverPointer = Join-Path $MirrorRoot "artifacts\trending\discover\v1\current.json"
        if (Test-Path -LiteralPath $discoverPointer -PathType Leaf) {
            & $Python -m scripts.rebuild_rardar_discover_serving --target $MirrorRoot
            if ($LASTEXITCODE -ne 0) {
                throw "Rardar Discover Serving rebuild failed; the active Today Serving pointer was preserved."
            }
        }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $savedPythonPath
        $env:DATABASE_URL = $savedDatabaseUrl
    }
}

function Refresh-RardarHotspotNews {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Existing TopicEye Python runtime is unavailable: $Python"
    }
    Start-Postgres
    $script:DatabaseUser = Resolve-DatabaseUser
    $database = Resolve-Database
    $encodedUser = [Uri]::EscapeDataString($script:DatabaseUser)
    $encodedDatabase = [Uri]::EscapeDataString($database)
    $databaseUrl = "postgresql+asyncpg://${encodedUser}@127.0.0.1:${PgPort}/${encodedDatabase}"
    $savedEnvironment = @{}
    $refreshEnvironment = @{
        DATABASE_URL = $databaseUrl
        RARDAR_PRODUCT_MODE = "true"
        PYTHONPATH = $BackendRoot
        PYTHONUTF8 = "1"
        PYTHONIOENCODING = "utf-8"
        RARDAR_LLM_RUN_ID = $null
        RARDAR_LLM_BUDGET_PATH = $null
        RARDAR_LLM_BUDGET_LIMIT = $null
    }
    foreach ($name in $refreshEnvironment.Keys) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $refreshEnvironment[$name], "Process")
    }
    Push-Location $BackendRoot
    try {
        & $Python -m scripts.refresh_rardar_hotspot_news
        if ($LASTEXITCODE -ne 0) { throw "Rardar Hotspot News refresh did not complete." }
    } finally {
        Pop-Location
        foreach ($name in $refreshEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
        }
    }
}

function Enhance-RardarHotspotNews {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Existing TopicEye Python runtime is unavailable: $Python"
    }
    if (-not $NewsBudgetPath -or -not [IO.Path]::IsPathFullyQualified($NewsBudgetPath) -or -not $NewsRunId) {
        throw "enhance-news requires absolute -NewsBudgetPath and -NewsRunId."
    }
    $resolvedBudgetPath = [IO.Path]::GetFullPath($NewsBudgetPath)
    if ($resolvedBudgetPath.StartsWith($RepoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "News budget must stay outside the repository."
    }
    Start-Postgres
    $script:DatabaseUser = Resolve-DatabaseUser
    $database = Resolve-Database
    $encodedUser = [Uri]::EscapeDataString($script:DatabaseUser)
    $encodedDatabase = [Uri]::EscapeDataString($database)
    $databaseUrl = "postgresql+asyncpg://${encodedUser}@127.0.0.1:${PgPort}/${encodedDatabase}"
    $savedEnvironment = @{}
    $enhanceEnvironment = @{
        DATABASE_URL = $databaseUrl
        RARDAR_PRODUCT_MODE = "true"
        APP_ENV = "development"
        PYTHONPATH = $BackendRoot
        PYTHONUTF8 = "1"
        PYTHONIOENCODING = "utf-8"
    }
    foreach ($name in $enhanceEnvironment.Keys) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $enhanceEnvironment[$name], "Process")
    }
    $arguments = @(
        "-m", "scripts.enhance_rardar_hotspot_news",
        "run",
        "--budget-path", $resolvedBudgetPath,
        "--run-id", $NewsRunId,
        "--limit", [string]$NewsBudgetLimit,
        "--item-limit", [string]$NewsItemLimit
    )
    Push-Location $BackendRoot
    try {
        if ($InitializeNewsBudget) {
            $initialize = @(
                "-m", "scripts.enhance_rardar_hotspot_news",
                "initialize-budget",
                "--budget-path", $resolvedBudgetPath,
                "--run-id", $NewsRunId,
                "--limit", [string]$NewsBudgetLimit
            )
            & $Python @initialize
            if ($LASTEXITCODE -ne 0) { throw "Rardar News budget initialization failed." }
        }
        & $Python @arguments
        if ($LASTEXITCODE -ne 0) { throw "Rardar News quick-read enhancement did not complete." }
    } finally {
        Pop-Location
        foreach ($name in $enhanceEnvironment.Keys) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
        }
    }
}

function Invoke-SelectionCommand([string[]]$Arguments) {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Existing TopicEye Python runtime is unavailable: $Python"
    }
    Start-Postgres
    $script:DatabaseUser = Resolve-DatabaseUser
    $database = Resolve-Database
    $encodedUser = [Uri]::EscapeDataString($script:DatabaseUser)
    $encodedDatabase = [Uri]::EscapeDataString($database)
    $databaseUrl = "postgresql+asyncpg://${encodedUser}@127.0.0.1:${PgPort}/${encodedDatabase}"
    $savedPythonPath = $env:PYTHONPATH
    $savedDatabaseUrl = $env:DATABASE_URL
    $env:PYTHONPATH = $BackendRoot
    $env:DATABASE_URL = $databaseUrl
    Push-Location $BackendRoot
    try {
        & $Python -m scripts.rebuild_rardar_discover_selection @Arguments --target $MirrorRoot
        if ($LASTEXITCODE -ne 0) { throw "Rardar worth-seeing Selection command failed." }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $savedPythonPath
        $env:DATABASE_URL = $savedDatabaseUrl
    }
}

function Build-RardarSelection {
    Invoke-SelectionCommand @("build")
}

function Show-RardarSelectionStatus {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Existing TopicEye Python runtime is unavailable: $Python"
    }
    # Selection status validates immutable filesystem data only.  Give the
    # application settings a syntactically valid, non-routable database URL so
    # this read-only command never starts PostgreSQL merely to inspect data.
    $savedPythonPath = $env:PYTHONPATH
    $savedDatabaseUrl = $env:DATABASE_URL
    $env:PYTHONPATH = $BackendRoot
    if (-not $env:DATABASE_URL) {
        $env:DATABASE_URL = "postgresql+asyncpg://status@127.0.0.1:1/status"
    }
    Push-Location $BackendRoot
    try {
        & $Python -m scripts.rebuild_rardar_discover_selection status --target $MirrorRoot
        if ($LASTEXITCODE -ne 0) { throw "Rardar worth-seeing Selection status failed." }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $savedPythonPath
        $env:DATABASE_URL = $savedDatabaseUrl
    }
}

function Rollback-RardarSelection {
    if (-not $SelectionGeneration) {
        throw "selection-rollback requires -SelectionGeneration <generation-id>."
    }
    Invoke-SelectionCommand @("rollback", $SelectionGeneration)
}

switch ($Command) {
    "start" { Start-Rardar }
    "stop" { Stop-Rardar }
    "status" { Show-Status; Show-RardarSelectionStatus }
    "sync-data" { Sync-RardarData }
    "refresh-news" { Refresh-RardarHotspotNews }
    "enhance-news" { Enhance-RardarHotspotNews }
    "rebuild-serving" { Rebuild-RardarServing }
    "build-selection" { Build-RardarSelection }
    "rebuild-selection" { Build-RardarSelection }
    "selection-status" { Show-RardarSelectionStatus }
    "selection-rollback" { Rollback-RardarSelection }
}
