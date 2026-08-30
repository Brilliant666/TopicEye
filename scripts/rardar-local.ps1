param(
    [ValidateSet("start", "stop", "status", "sync-data", "rebuild-serving")]
    [string]$Command = "start"
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

function Show-Status {
    $state = Read-State
    $postgresHealthy = (& $PgReady -h 127.0.0.1 -p $PgPort 2>$null) -match "accepting connections"
    [pscustomobject]@{
        Repository = $RepoRoot
        PostgreSQL = if ($postgresHealthy) { "healthy" } else { "stopped" }
        Backend = if ($state -and (Test-Process $state.backendPid) -and (Test-Http "http://127.0.0.1:8102/health/live")) { "healthy" } else { "stopped" }
        Frontend = if ($state -and (Test-Process $state.frontendPid) -and (Test-Http "http://127.0.0.1:3000/api/health")) { "healthy" } else { "stopped" }
        DataMode = if ($state -and $state.dataMode) { $state.dataMode } elseif ($env:RARDAR_DATA_MODE) { $env:RARDAR_DATA_MODE } else { "real" }
        DataMirror = $MirrorRoot
        DataSynced = if (Test-Path -LiteralPath (Join-Path $MirrorRoot "serving\current.json") -PathType Leaf) { "yes" } else { "no; run rebuild-serving" }
        Product = "http://127.0.0.1:3000/"
        Login = "http://127.0.0.1:3000/login"
        Admin = "http://127.0.0.1:3000/admin"
        Models = "http://127.0.0.1:3000/admin/model-eval"
    } | Format-List
}

function Stop-AppProcess([object]$ProcessId, [string]$ExpectedName) {
    if (-not (Test-Process $ProcessId)) { return }
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

function Stop-Rardar {
    $state = Read-State
    if ($state) {
        if (-not $state.repository -or $state.repository -ne $RepoRoot) {
            throw "Refusing to use local runtime state owned by another repository."
        }
        Stop-AppProcess $state.frontendPid "^(node|cmd)\.exe$"
        Stop-AppProcess $state.backendPid "^python(w)?\.exe$"
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
    if ((& $PgReady -h 127.0.0.1 -p $PgPort 2>$null) -match "accepting connections") { return }

    $pidPath = Join-Path $PgData "postmaster.pid"
    if (Test-Path -LiteralPath $pidPath) {
        $recordedPid = Get-Content -LiteralPath $pidPath -TotalCount 1
        if (-not (Test-Process $recordedPid)) {
            Remove-Item -LiteralPath $pidPath -Force
        }
    }
    $pgLog = Join-Path $ControlRoot "postgres.log"
    & $PgCtl start -D $PgData -l $pgLog -o "-p $PgPort -h 127.0.0.1" -w
    if ($LASTEXITCODE -ne 0 -or -not ((& $PgReady -h 127.0.0.1 -p $PgPort 2>$null) -match "accepting connections")) {
        throw "Existing TopicEye PostgreSQL could not be started; see $pgLog"
    }
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
    $existing = Read-State
    if ($existing -and (Test-Process $existing.backendPid) -and (Test-Process $existing.frontendPid)) {
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
    $dataMode = if ($env:RARDAR_DATA_MODE) { $env:RARDAR_DATA_MODE.Trim().ToLowerInvariant() } else { "real" }
    if ($dataMode -notin @("real", "demo")) {
        throw 'RARDAR_DATA_MODE must be "real" or "demo".'
    }

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
        RARDAR_INTELLIGENCE_DATA_DIR = $MirrorRoot
        CORS_ORIGINS = "http://127.0.0.1:3000"
        SCHEDULER_ENABLED = "false"
        CACHE_WARMUP_ENABLED = "false"
        DUCKDB_STARTUP_INIT_ENABLED = "false"
        STARTUP_SEED_ENABLED = "false"
        ADMIN_SEED_ENABLED = "false"
        PYTHONUTF8 = "1"
        PYTHONIOENCODING = "utf-8"
    }
    foreach ($name in $backendEnvironment.Keys) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $backendEnvironment[$name], "Process")
    }
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
        $savedProductMode = $env:RARDAR_PRODUCT_MODE
        $savedBackendUrl = $env:BACKEND_API_URL
        $env:RARDAR_PRODUCT_MODE = "true"
        $env:BACKEND_API_URL = "http://127.0.0.1:8102"
        try {
            $next = Join-Path $FrontendRoot "node_modules\next\dist\bin\next"
            $frontend = Start-Process -FilePath $Node -ArgumentList @($next, "dev", "--webpack", "--hostname", "127.0.0.1", "--port", "3000") -WorkingDirectory $FrontendRoot -RedirectStandardOutput (Join-Path $RuntimeRoot "frontend.out.log") -RedirectStandardError (Join-Path $RuntimeRoot "frontend.err.log") -WindowStyle Hidden -PassThru
        } finally {
            $env:RARDAR_PRODUCT_MODE = $savedProductMode
            $env:BACKEND_API_URL = $savedBackendUrl
        }
        Wait-Http "http://127.0.0.1:3000/api/health" 120
    } catch {
        if ($frontend -and (Test-Process $frontend.Id)) { & taskkill.exe /PID $frontend.Id /T /F | Out-Null }
        if (Test-Process $backend.Id) { & taskkill.exe /PID $backend.Id /T /F | Out-Null }
        throw
    }

    [pscustomobject]@{
        schemaVersion = 1
        repository = $RepoRoot
        startedAt = (Get-Date).ToUniversalTime().ToString("o")
        backendPid = $backend.Id
        frontendPid = $frontend.Id
        postgresPort = $PgPort
        database = $database
        dataMode = $dataMode
        dataMirror = $MirrorRoot
    } | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding utf8
    Show-Status
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
            throw "Rardar Discover sync failed after the independent Today sync; the active Today pointer was preserved."
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

switch ($Command) {
    "start" { Start-Rardar }
    "stop" { Stop-Rardar }
    "status" { Show-Status }
    "sync-data" { Sync-RardarData }
    "rebuild-serving" { Rebuild-RardarServing }
}
