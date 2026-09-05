[CmdletBinding()]
param(
    [string]$RepoRoot,
    [int]$Port = 8015
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
}
else {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
}

& uv sync --project (Join-Path $RepoRoot 'backend') --extra dev --frozen
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed with exit code $LASTEXITCODE"
}

$artifactRoot = Join-Path ([System.IO.Path]::GetTempPath()) "ragops-offline-$([Guid]::NewGuid())"
New-Item -ItemType Directory -Path $artifactRoot | Out-Null
$databasePath = Join-Path $artifactRoot 'ragops.sqlite'
$statePath = Join-Path $artifactRoot 'state.json'
$stdoutPath = Join-Path $artifactRoot 'backend.stdout.log'
$stderrPath = Join-Path $artifactRoot 'backend.stderr.log'
$baseUrl = "http://127.0.0.1:$Port"

$environmentNames = @(
    'RAGOPS_DATABASE_URL',
    'RAGOPS_AUTO_CREATE_SCHEMA',
    'RAGOPS_MODEL_EXECUTION_ADAPTER',
    'RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED'
)
$previousEnvironment = @{}
foreach ($name in $environmentNames) {
    $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}

$env:RAGOPS_DATABASE_URL = "sqlite:///$($databasePath.Replace('\', '/'))"
$env:RAGOPS_AUTO_CREATE_SCHEMA = 'true'
$env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
$env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'

$uvicorn = if ($env:OS -eq 'Windows_NT') {
    Join-Path $RepoRoot 'backend\.venv\Scripts\uvicorn.exe'
}
else {
    Join-Path $RepoRoot 'backend/.venv/bin/uvicorn'
}
if (-not (Test-Path $uvicorn -PathType Leaf)) {
    throw "uvicorn executable not found after uv sync: $uvicorn"
}

function Start-Backend {
    $arguments = @{
        FilePath = $uvicorn
        ArgumentList = @('app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', "$Port")
        WorkingDirectory = $RepoRoot
        PassThru = $true
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
    }
    if ($env:OS -eq 'Windows_NT') {
        $arguments.WindowStyle = 'Hidden'
    }
    return Start-Process @arguments
}

function Wait-Ready {
    param([System.Diagnostics.Process]$Process)
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(30)
    do {
        if ($Process.HasExited) {
            throw "Backend exited before readiness. See $stderrPath"
        }
        try {
            $ready = Invoke-RestMethod -Uri "$baseUrl/health/ready" -TimeoutSec 2
            if ($ready.status -eq 'ready') {
                return
            }
        }
        catch {
        }
        Start-Sleep -Milliseconds 250
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "Backend did not become ready. See $stderrPath"
}

function Stop-Backend {
    param([System.Diagnostics.Process]$Process)
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id
        $Process.WaitForExit(5000)
    }
}

$backend = $null
try {
    $backend = Start-Backend
    Wait-Ready -Process $backend
    & (Join-Path $PSScriptRoot 'invoke-api-loop.ps1') -BaseUrl $baseUrl -StatePath $statePath
    if ($LASTEXITCODE -ne 0) {
        throw "Initial API loop failed with exit code $LASTEXITCODE"
    }
    Stop-Backend -Process $backend

    $backend = Start-Backend
    Wait-Ready -Process $backend
    & (Join-Path $PSScriptRoot 'invoke-api-loop.ps1') -BaseUrl $baseUrl -ExistingStatePath $statePath
    if ($LASTEXITCODE -ne 0) {
        throw "Restart persistence check failed with exit code $LASTEXITCODE"
    }
    Write-Output "Local restart acceptance passed. Evidence: $artifactRoot"
}
finally {
    Stop-Backend -Process $backend
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
    }
}
