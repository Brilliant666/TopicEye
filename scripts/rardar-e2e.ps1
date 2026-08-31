param(
    [int]$FrontendPort = 3420,
    [int]$BackendPort = 3421
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendRoot = Join-Path $RepoRoot "backend"
$FrontendRoot = Join-Path $RepoRoot "frontend"
$RuntimeRoot = Join-Path $env:TEMP ("rardar-mvp-e2e-" + [guid]::NewGuid().ToString("N"))
$ModeFile = Join-Path $RuntimeRoot "mode.txt"
$MirrorRoot = Join-Path $RuntimeRoot "rardar-intelligence"
$Python = Join-Path $env:LOCALAPPDATA "TopicEyeRardarLLMControl\venv-20260826\Scripts\python.exe"
$Node = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"

foreach ($required in @($Python, $Node)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required local runtime is missing: $required"
    }
}
if (Get-NetTCPConnection -LocalPort $FrontendPort, $BackendPort -State Listen -ErrorAction SilentlyContinue) {
    throw "The isolated E2E ports are already occupied."
}

New-Item -ItemType Directory -Path $RuntimeRoot | Out-Null
[IO.File]::WriteAllText($ModeFile, "top20`n", [Text.UTF8Encoding]::new($false))
New-Item -ItemType Directory -Path $MirrorRoot | Out-Null
Copy-Item -Path (Join-Path $BackendRoot "tests\fixtures\rardar_intelligence\revision-a\*") -Destination $MirrorRoot -Recurse
Copy-Item -Path (Join-Path $BackendRoot "tests\fixtures\rardar_discover\artifacts") -Destination $MirrorRoot -Recurse

# Git may materialize JSON fixture text with CRLF on Windows even though the
# immutable producer hashes were calculated over canonical LF bytes. Normalize
# only the temporary copy so process-level safe-read tests exercise the same
# bytes as Linux CI without rewriting checked-in fixtures.
Get-ChildItem -LiteralPath (Join-Path $MirrorRoot "artifacts") -Filter "*.json" -Recurse | ForEach-Object {
    $raw = [IO.File]::ReadAllBytes($_.FullName)
    $text = [Text.UTF8Encoding]::new($false, $true).GetString($raw)
    if ($text.Contains("`r`n")) {
        [IO.File]::WriteAllText($_.FullName, $text.Replace("`r`n", "`n"), [Text.UTF8Encoding]::new($false))
    }
}

# Next's persistent fetch cache must not leak a prior E2E mode into this run.
# The path is verified before deleting generated build output.
$nextOutput = Join-Path $FrontendRoot ".next"
if (Test-Path -LiteralPath $nextOutput) {
    $resolvedNextOutput = (Resolve-Path -LiteralPath $nextOutput).Path
    if (
        (Split-Path $resolvedNextOutput -Parent) -ne $FrontendRoot `
        -or (Split-Path $resolvedNextOutput -Leaf) -ne ".next"
    ) {
        throw "Refusing to remove an unexpected Next output path: $resolvedNextOutput"
    }
    Remove-Item -LiteralPath $resolvedNextOutput -Recurse -Force
}

$env:PYTHONPATH = $BackendRoot
$env:DATABASE_URL = "postgresql+asyncpg://adapter:adapter@127.0.0.1:5432/adapter"
$env:RARDAR_PRODUCT_MODE = "true"
$env:RARDAR_DATA_MODE = "real"
$env:RARDAR_DEMO_DATA_ENABLED = "false"
$env:RARDAR_INTELLIGENCE_DATA_DIR = $MirrorRoot
$env:RARDAR_ADAPTER_TEST_MODE_FILE = $ModeFile
$env:BACKEND_API_URL = "http://127.0.0.1:$BackendPort"
$env:RARDAR_E2E_BASE_URL = "http://127.0.0.1:$FrontendPort"
$env:RARDAR_E2E_MODE_FILE = $ModeFile

Push-Location $BackendRoot
try {
    & $Python -m scripts.rebuild_rardar_serving --target $MirrorRoot --translate-top 0 --offline
    if ($LASTEXITCODE -ne 0) { throw "Could not build the isolated Serving Projection." }
    & $Python -m tests_rardar_adapter.build_discover_e2e_fixture --target $MirrorRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not build the isolated Discover Serving Projection." }
} finally {
    Pop-Location
}

$backend = $null
$frontend = $null
$succeeded = $false
try {
    $backend = Start-Process -FilePath $Python `
        -ArgumentList @("-m", "uvicorn", "tests_rardar_adapter.http_app:app", "--host", "127.0.0.1", "--port", "$BackendPort", "--log-level", "warning") `
        -WorkingDirectory $BackendRoot `
        -RedirectStandardOutput (Join-Path $RuntimeRoot "backend.out.log") `
        -RedirectStandardError (Join-Path $RuntimeRoot "backend.err.log") `
        -WindowStyle Hidden `
        -PassThru

    $backendDeadline = (Get-Date).AddSeconds(30)
    $backendReady = $false
    do {
        Start-Sleep -Milliseconds 250
        try {
            $backendReady = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$BackendPort/openapi.json" -TimeoutSec 2).StatusCode -eq 200
        } catch {
            $backendReady = $false
        }
    } until ($backendReady -or (Get-Date) -gt $backendDeadline -or $backend.HasExited)
    if (-not $backendReady) {
        throw "The isolated Rardar E2E backend did not become ready. Logs: $RuntimeRoot"
    }

    Push-Location $FrontendRoot
    try {
        & $Node "node_modules/next/dist/bin/next" build
        if ($LASTEXITCODE -ne 0) { throw "Could not build the isolated production frontend." }
    } finally {
        Pop-Location
    }

    $frontend = Start-Process -FilePath $Node `
        -ArgumentList @("node_modules/next/dist/bin/next", "start", "-H", "127.0.0.1", "-p", "$FrontendPort") `
        -WorkingDirectory $FrontendRoot `
        -RedirectStandardOutput (Join-Path $RuntimeRoot "frontend.out.log") `
        -RedirectStandardError (Join-Path $RuntimeRoot "frontend.err.log") `
        -WindowStyle Hidden `
        -PassThru

    $deadline = (Get-Date).AddSeconds(60)
    $ready = $false
    do {
        Start-Sleep -Milliseconds 500
        try {
            $ready = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$FrontendPort/api/health" -TimeoutSec 2).StatusCode -eq 200
        } catch {
            $ready = $false
        }
    } until ($ready -or (Get-Date) -gt $deadline -or $backend.HasExited -or $frontend.HasExited)
    if (-not $ready) {
        throw "The isolated Rardar E2E servers did not become ready. Logs: $RuntimeRoot"
    }

    Push-Location $FrontendRoot
    try {
        & $Node "node_modules/@playwright/test/cli.js" test "e2e/rardar-intelligence.spec.ts"
        if ($LASTEXITCODE -ne 0) {
            throw "Playwright failed with exit code $LASTEXITCODE. Logs: $RuntimeRoot"
        }
        $succeeded = $true
    } finally {
        Pop-Location
    }
} finally {
    foreach ($process in @($frontend, $backend)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if ($succeeded) {
        $resolvedTemp = (Resolve-Path $env:TEMP).Path
        $resolvedRuntime = (Resolve-Path $RuntimeRoot).Path
        if (
            (Split-Path $resolvedRuntime -Parent) -ne $resolvedTemp `
            -or (Split-Path $resolvedRuntime -Leaf) -notlike "rardar-mvp-e2e-*"
        ) {
            throw "Refusing to remove an unexpected E2E runtime path: $resolvedRuntime"
        }
        Remove-Item -LiteralPath $resolvedRuntime -Recurse -Force
    }
}

Write-Output "Rardar isolated Playwright suite passed; temporary runtime was removed."
