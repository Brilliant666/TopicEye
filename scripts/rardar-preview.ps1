# Loaded by rardar-local.ps1. No standalone process manager or background service.
function Get-PreviewHash([string]$Value) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData(
        [Text.Encoding]::UTF8.GetBytes($Value))).ToLowerInvariant()
}

function Write-PreviewJson([string]$Path, [object]$Value) {
    $temporary = "$Path.$PID.tmp"
    try {
        [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
        [IO.File]::Move($temporary, $Path, $true)
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
    }
}

function Read-PreviewJson([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    return $null
}

function Assert-PreviewPath([string]$Path) {
    if (-not [IO.Path]::IsPathFullyQualified($Path) -or $Path -match '[\r\n"\x00]') {
        throw "Preview configuration requires a safe absolute path."
    }
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (-not $item.PSIsContainer) { throw "Preview data paths must be directories." }
    while ($item) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Preview configuration cannot traverse reparse points."
        }
        $item = $item.Parent
    }
}

function Get-PreviewConfig {
    $config = Read-PreviewJson $script:PreviewConfigPath
    if (-not $config) {
        # Local-only defaults. Subsequent calls read this managed configuration.
        # No password/key is stored, and no data or budget is copied/initialized.
        $original = Read-State
        if (-not $original -or -not $original.database) {
            throw "Original Runtime database identity is missing; configure the managed preview config first."
        }
        $config = [pscustomobject]@{
            schemaVersion = 1; repository = $RepoRoot
            backendPort = 54191; frontendPort = 54190; postgresPort = $PgPort
            dataDirectory = (Join-Path $env:TEMP "rardar-refocus-preview-data")
            budgetIdentityDataDirectory = $MirrorRoot
            database = $original.database; databaseUser = "topiceye"
        }
        Write-PreviewJson $script:PreviewConfigPath $config
    }
    $allowed = @("schemaVersion", "repository", "backendPort", "frontendPort", "postgresPort",
        "dataDirectory", "budgetIdentityDataDirectory", "database", "databaseUser")
    if ($config.schemaVersion -ne 1 -or $config.repository -ine $RepoRoot -or
        @($config.PSObject.Properties.Name | Where-Object { $_ -notin $allowed }).Count) {
        throw "Preview configuration schema or repository does not match."
    }
    foreach ($port in @($config.backendPort, $config.frontendPort)) {
        if (($port -isnot [int] -and $port -isnot [long]) -or $port -lt 1024 -or $port -gt 65535 -or $port -in @(3000, 8102, $config.postgresPort)) {
            throw "Preview ports must be distinct from the original Runtime and PostgreSQL."
        }
    }
    if ($config.backendPort -eq $config.frontendPort -or $config.postgresPort -ne $PgPort) {
        throw "Preview port configuration does not match the original database."
    }
    foreach ($path in @($config.dataDirectory, $config.budgetIdentityDataDirectory)) { Assert-PreviewPath $path }
    if ([IO.Path]::GetFullPath($config.dataDirectory).TrimEnd('\') -ieq [IO.Path]::GetFullPath($MirrorRoot).TrimEnd('\') -or
        [IO.Path]::GetFullPath($config.budgetIdentityDataDirectory).TrimEnd('\') -ine [IO.Path]::GetFullPath($MirrorRoot).TrimEnd('\')) {
        throw "Preview data must be isolated and its budget identity must remain the original Runtime identity."
    }
    foreach ($value in @($config.database, $config.databaseUser)) {
        if ($value -notmatch '^[A-Za-z_][A-Za-z0-9_-]{0,62}$') { throw "Invalid local database identity." }
    }
    return $config
}

function Get-PreviewSourceFingerprint {
    $entries = @(& git -C $RepoRoot ls-files -- frontend)
    if ($LASTEXITCODE -ne 0 -or -not $entries.Count) { throw "Cannot inspect frontend inputs." }
    $values = foreach ($entry in ($entries | Sort-Object)) {
        $path = Join-Path $RepoRoot $entry
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Frontend tracked input missing." }
        "$entry=$((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash)"
    }
    # Untracked source and local frontend env files affect a build as well.
    $extra = @(& git -C $RepoRoot ls-files --others --exclude-standard -- frontend)
    if ($extra.Count) { throw "Untracked frontend inputs must be reviewed before building." }
    foreach ($envFile in @(Get-ChildItem -LiteralPath $FrontendRoot -Filter '.env*' -File -Force)) {
        $values += "$($envFile.Name)=$((Get-FileHash -LiteralPath $envFile.FullName -Algorithm SHA256).Hash)"
    }
    return Get-PreviewHash ($values -join "`n")
}

function Get-PreviewBuild([object]$Config) {
    $manifest = Read-PreviewJson $script:PreviewBuildPath
    $buildIdPath = Join-Path $FrontendRoot '.next-preview\BUILD_ID'
    $routesPath = Join-Path $FrontendRoot '.next-preview\routes-manifest.json'
    if (-not $manifest -or -not (Test-Path -LiteralPath $buildIdPath) -or -not (Test-Path -LiteralPath $routesPath)) {
        throw "Preview build provenance missing. Run preview-build once; ordinary start never rebuilds."
    }
    $buildId = (Get-Content -LiteralPath $buildIdPath -Raw).Trim()
    $routes = Read-PreviewJson $routesPath
    $rewrite = @($routes.rewrites.afterFiles | Where-Object source -eq '/api/:path*')
    if ($manifest.sourceFingerprint -ne (Get-PreviewSourceFingerprint) -or $manifest.buildId -ne $buildId -or
        $manifest.backendPort -ne $Config.backendPort -or $manifest.productMode -ne $true -or
        $manifest.routesHash -ne (Get-FileHash -LiteralPath $routesPath -Algorithm SHA256).Hash -or
        $rewrite.Count -ne 1 -or $rewrite[0].destination -ne "http://127.0.0.1:$($Config.backendPort)/api/:path*") {
        throw "Preview build mismatch. Stop the owned preview and run preview-build; no process was stopped."
    }
    return $manifest
}

function Assert-PreviewDatabase([object]$Config) {
    $listener = Get-LoopbackListenerPid $Config.postgresPort
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $listener"
    if ($process.ExecutablePath -ine (Join-Path $PgRoot 'bin\postgres.exe') -or
        -not $process.CommandLine -or $process.CommandLine.Replace('/', '\').IndexOf($PgData, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "Original PostgreSQL identity could not be verified. Preview does not start or repair databases."
    }
    $answer = & $Psql -w -h 127.0.0.1 -p $Config.postgresPort -U $Config.databaseUser -d $Config.database -At -c 'select current_database(), current_user' 2>$null
    if ($LASTEXITCODE -ne 0 -or $answer.Trim() -ne "$($Config.database)|$($Config.databaseUser)") {
        throw "Original PostgreSQL database/role is unavailable; no database changes were attempted."
    }
}

function Get-PreviewProcessRecord([int]$ProcessId, [int]$Port) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
    if (-not $process -or -not $process.ExecutablePath -or -not $process.CommandLine) { throw "Cannot record preview process identity." }
    return [pscustomobject]@{
        pid = $ProcessId; port = $Port; executable = $process.ExecutablePath
        createdAt = $process.CreationDate.ToUniversalTime().ToString('o')
        commandHash = Get-PreviewHash $process.CommandLine
        listener = $null
    }
}

function Assert-PreviewProcess([object]$Record, [bool]$RequireListener = $true) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($Record.pid)" -ErrorAction SilentlyContinue
    if (-not $process) {
        if ($Record.listener -and (Test-Process $Record.listener.pid)) { throw "Preview parent disappeared but listener remains; manual identity review required." }
        if (Get-NetTCPConnection -LocalPort $Record.port -State Listen -ErrorAction SilentlyContinue) { throw "Unowned process occupies preview port." }
        return $false
    }
    if ($Record.executable -notin @($Python, $Node) -or $process.ExecutablePath -ine $Record.executable -or
        $process.CreationDate.ToUniversalTime().ToString('o') -ne $Record.createdAt -or
        (Get-PreviewHash $process.CommandLine) -ne $Record.commandHash -or
        $process.CommandLine.IndexOf($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or
        $process.ExecutablePath -in @((Join-Path $PgRoot 'bin\postgres.exe'), $PgCtl)) {
        throw "Preview process identity changed; refusing process control."
    }
    if ($RequireListener) {
        $listenerId = Get-LoopbackListenerPid $Record.port
        if (-not $Record.listener -or $listenerId -ne $Record.listener.pid -or
            -not (Test-ProcessDescendsFrom $listenerId $Record.pid)) { throw "Preview listener ownership mismatch." }
        $listener = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerId"
        if ($listener.ExecutablePath -ine $Record.listener.executable -or
            $listener.CreationDate.ToUniversalTime().ToString('o') -ne $Record.listener.createdAt -or
            (Get-PreviewHash $listener.CommandLine) -ne $Record.listener.commandHash) { throw "Preview listener identity changed." }
    }
    return $true
}

function Stop-PreviewState([object]$State) {
    if (-not $State) { return }
    if ($State.repository -ine $RepoRoot) { throw "Preview state belongs to another worktree." }
    $records = @($State.frontend, $State.backend) | Where-Object { $_ }
    # Validate every live root before terminating any, including PID-reuse guards.
    foreach ($record in $records) { $null = Assert-PreviewProcess $record ([bool]$record.listener) }
    foreach ($record in $records) {
        if (Assert-PreviewProcess $record ([bool]$record.listener)) {
            & taskkill.exe /PID $record.pid /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Preview stop failed; ownership state retained." }
        }
    }
    foreach ($record in $records) {
        $deadline = (Get-Date).AddSeconds(8)
        while ((Test-Process $record.pid) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
        if (Test-Process $record.pid) { throw "Preview process still alive; state retained." }
        if (Get-NetTCPConnection -LocalPort $record.port -State Listen -ErrorAction SilentlyContinue) { throw "Preview port remains occupied; state retained." }
    }
    Remove-Item -LiteralPath $script:PreviewStatePath -ErrorAction SilentlyContinue
}

function Test-PreviewState([object]$State, [object]$Config, [object]$Build, [string]$Head) {
    if (-not $State -or $State.status -ne 'healthy') { return $false }
    if ($State.repository -ine $RepoRoot -or $State.head -ne $Head -or
        $State.configHash -ne (Get-PreviewHash ($Config | ConvertTo-Json -Compress)) -or $State.buildId -ne $Build.buildId) {
        throw "Preview version/configuration changed; use preview-restart after preflight."
    }
    return (Assert-PreviewProcess $State.backend) -and (Assert-PreviewProcess $State.frontend) -and
        (Test-Http "http://127.0.0.1:$($Config.backendPort)/health/live") -and
        (Test-Http "http://127.0.0.1:$($Config.frontendPort)/api/health")
}

function Invoke-RardarPreview([string]$Action) {
    if ($PSVersionTable.PSVersion -lt [version]'7.4') { throw "Preview requires PowerShell 7.4 or newer; no policy override is used." }
    $identity = (Get-PreviewHash $RepoRoot.ToLowerInvariant()).Substring(0, 16)
    $script:PreviewRoot = Join-Path $env:LOCALAPPDATA "TopicEye\rardar-previews\$identity"
    New-Item -ItemType Directory -Path $script:PreviewRoot -Force | Out-Null
    $script:PreviewConfigPath = Join-Path $script:PreviewRoot 'config.json'
    $script:PreviewStatePath = Join-Path $script:PreviewRoot 'runtime.json'
    $script:PreviewBuildPath = Join-Path $script:PreviewRoot 'build.json'
    $lock = $null
    try {
        $lock = [IO.File]::Open((Join-Path $script:PreviewRoot 'operation.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
        $state = Read-PreviewJson $script:PreviewStatePath
        if ($Action -eq 'preview-stop') {
            Stop-PreviewState $state
            Write-Host 'Preview stopped. Shared PostgreSQL and original Runtime were not stopped.'
            return
        }
        $config = Get-PreviewConfig
        $head = (& git -C $RepoRoot rev-parse HEAD).Trim()
        if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[a-f0-9]{40}$') { throw "Cannot identify preview HEAD." }
        foreach ($required in @($Python, $Node, $Psql, (Join-Path $FrontendRoot 'node_modules\next\dist\bin\next'))) {
            if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Preview dependency missing: $required" }
        }
        $frontendEnvironment = @{
            NODE_ENV = 'production'; RARDAR_PRODUCT_MODE = 'true'; RARDAR_ISOLATED_PREVIEW = 'true'
            BACKEND_API_URL = "http://127.0.0.1:$($config.backendPort)"; NEXT_TELEMETRY_DISABLED = '1'
        }
        $next = Join-Path $FrontendRoot 'node_modules\next\dist\bin\next'
        if ($Action -eq 'preview-build') {
            if (($state -and ((Test-Process $state.frontend.pid) -or (Test-Process $state.backend.pid))) -or
                (Get-NetTCPConnection -LocalPort $config.frontendPort -State Listen -ErrorAction SilentlyContinue)) {
                throw "Stop the preview before replacing its production build."
            }
            $fingerprint = Get-PreviewSourceFingerprint
            $saved = @{}
            try {
                foreach ($key in $frontendEnvironment.Keys) {
                    $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
                    [Environment]::SetEnvironmentVariable($key, $frontendEnvironment[$key], 'Process')
                }
                Push-Location $FrontendRoot
                try { & $Node $next build --webpack; $exitCode = $LASTEXITCODE } finally { Pop-Location }
            } finally {
                foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
            }
            if ($exitCode -ne 0 -or $fingerprint -ne (Get-PreviewSourceFingerprint)) { throw "Preview build failed or inputs changed." }
            Write-PreviewJson $script:PreviewBuildPath ([pscustomobject]@{
                sourceFingerprint = $fingerprint; backendPort = $config.backendPort; productMode = $true
                buildId = (Get-Content -LiteralPath (Join-Path $FrontendRoot '.next-preview\BUILD_ID') -Raw).Trim()
                routesHash = (Get-FileHash -LiteralPath (Join-Path $FrontendRoot '.next-preview\routes-manifest.json') -Algorithm SHA256).Hash
            })
            $null = Get-PreviewBuild $config
            Write-Host 'Preview production build recorded. No application or database was started.'
            return
        }
        $build = Get-PreviewBuild $config
        Assert-PreviewDatabase $config
        if ($Action -eq 'preview-status') {
            $healthy = Test-PreviewState $state $config $build $head
            [pscustomobject]@{ healthy = $healthy; head = $head; product = "http://127.0.0.1:$($config.frontendPort)";
                backend = "http://127.0.0.1:$($config.backendPort)"; config = $script:PreviewConfigPath; logs = $script:PreviewRoot } | Format-List
            if (-not $healthy) { throw "Preview is not healthy or not managed by this entry." }
            return
        }
        $dirty = & git -C $RepoRoot status --short --untracked-files=all
        if ($LASTEXITCODE -ne 0 -or $dirty) { throw "Preview startup requires a clean source tree so HEAD identifies the actual code." }
        if ($Action -eq 'preview-start' -and (Test-PreviewState $state $config $build $head)) {
            Write-Host "Preview already healthy: http://127.0.0.1:$($config.frontendPort)"; return
        }
        # All file/build/database checks precede stop. Unknown ports are never adopted.
        foreach ($port in @($config.frontendPort, $config.backendPort)) {
            if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
                $record = @($state.frontend, $state.backend) | Where-Object { $_ -and $_.port -eq $port }
                if (@($record).Count -ne 1) { throw "Unmanaged listener on preview port $port; no process was stopped." }
                $null = Assert-PreviewProcess $record
            }
        }
        if ($state) { Stop-PreviewState $state }
        $environment = @{
            DATABASE_URL = "postgresql+asyncpg://$($config.databaseUser)@127.0.0.1:$($config.postgresPort)/$($config.database)"
            APP_ENV = 'development'; RARDAR_PRODUCT_MODE = 'true'; RARDAR_DATA_MODE = 'real'; RARDAR_DEMO_DATA_ENABLED = 'false'
            RARDAR_LOCAL_SHADOW_REVIEW = 'false'
            RARDAR_INTELLIGENCE_DATA_DIR = $config.dataDirectory; RARDAR_BUDGET_IDENTITY_DATA_DIR = $config.budgetIdentityDataDirectory
            RARDAR_DAILY_OPERATIONS_ENABLED = 'true'; SCHEDULER_ENABLED = 'false'; CACHE_WARMUP_ENABLED = 'false'
            DUCKDB_STARTUP_INIT_ENABLED = 'false'; STARTUP_SEED_ENABLED = 'false'; ADMIN_SEED_ENABLED = 'false'
            CORS_ORIGINS = "http://127.0.0.1:$($config.frontendPort)"; PYTHONPATH = $BackendRoot; PYTHONUTF8 = '1'; PYTHONIOENCODING = 'utf-8'
            RARDAR_LLM_RUN_ID = $null; RARDAR_LLM_BUDGET_PATH = $null; RARDAR_LLM_BUDGET_LIMIT = $null
        }
        $state = [pscustomobject]@{ repository = $RepoRoot; head = $head; status = 'starting';
            configHash = Get-PreviewHash ($config | ConvertTo-Json -Compress); buildId = $build.buildId; backend = $null; frontend = $null }
        try {
            $backend = Start-AppProcess $Python @('-m', 'uvicorn', 'app.main:app', '--app-dir', "`"$BackendRoot`"", '--host', '127.0.0.1', '--port', "$($config.backendPort)", '--lifespan', 'off') $BackendRoot (Join-Path $script:PreviewRoot 'backend') $environment
            $state.backend = Get-PreviewProcessRecord $backend.Id $config.backendPort
            Write-PreviewJson $script:PreviewStatePath $state
            Wait-Http "http://127.0.0.1:$($config.backendPort)/health/live" 120
            $listenerId = Get-LoopbackListenerPid $config.backendPort
            if (-not (Test-ProcessDescendsFrom $listenerId $backend.Id)) { throw "Backend listener is not the started child." }
            $state.backend.listener = Get-PreviewProcessRecord $listenerId $config.backendPort
            Write-PreviewJson $script:PreviewStatePath $state
            $frontend = Start-AppProcess $Node @("`"$next`"", 'start', '--hostname', '127.0.0.1', '--port', "$($config.frontendPort)") $FrontendRoot (Join-Path $script:PreviewRoot 'frontend') $frontendEnvironment
            $state.frontend = Get-PreviewProcessRecord $frontend.Id $config.frontendPort
            Write-PreviewJson $script:PreviewStatePath $state
            Wait-Http "http://127.0.0.1:$($config.frontendPort)/api/health" 120
            $listenerId = Get-LoopbackListenerPid $config.frontendPort
            if (-not (Test-ProcessDescendsFrom $listenerId $frontend.Id)) { throw "Frontend listener is not the started child." }
            $state.frontend.listener = Get-PreviewProcessRecord $listenerId $config.frontendPort
            $state.status = 'healthy'
            Write-PreviewJson $script:PreviewStatePath $state
            if (-not (Test-PreviewState $state $config $build $head)) { throw "Preview post-start validation failed." }
            Write-Host "Preview healthy: http://127.0.0.1:$($config.frontendPort) (production). No terminal needs to stay open."
        } catch {
            $failure = $_
            try { Stop-PreviewState $state } catch { throw "Preview startup failed; cleanup requires identity review. Logs: $script:PreviewRoot" }
            throw $failure
        }
    } finally {
        if ($lock) { $lock.Dispose() }
    }
}
