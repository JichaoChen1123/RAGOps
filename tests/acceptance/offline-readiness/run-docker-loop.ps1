[CmdletBinding()]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
}
else {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
}

$projectName = "ragops-offline-$(([Guid]::NewGuid().ToString('N')).Substring(0, 12))"
$artifactRoot = Join-Path ([System.IO.Path]::GetTempPath()) $projectName
New-Item -ItemType Directory -Path $artifactRoot | Out-Null
$statePath = Join-Path $artifactRoot 'state.json'
$baseUrl = 'http://127.0.0.1:8000'

function Invoke-Compose {
    param([string[]]$Arguments)
    & docker compose --project-name $projectName --project-directory $RepoRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

function Wait-Ready {
    $deadline = [DateTimeOffset]::UtcNow.AddSeconds(60)
    do {
        try {
            $ready = Invoke-RestMethod -Uri "$baseUrl/health/ready" -TimeoutSec 2
            if ($ready.status -eq 'ready') {
                return
            }
        }
        catch {
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw 'Docker backend did not become ready within 60 seconds'
}

$previousAdapter = $env:RAGOPS_MODEL_EXECUTION_ADAPTER
$previousExternalCalls = $env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED
try {
    $env:RAGOPS_MODEL_EXECUTION_ADAPTER = 'mock'
    $env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = 'false'
    Invoke-Compose -Arguments @('config', '--quiet')
    Invoke-Compose -Arguments @('up', '--detach', '--build')
    Wait-Ready
    & (Join-Path $PSScriptRoot 'invoke-api-loop.ps1') -BaseUrl $baseUrl -StatePath $statePath
    if ($LASTEXITCODE -ne 0) {
        throw "Initial Docker API loop failed with exit code $LASTEXITCODE"
    }
    Invoke-Compose -Arguments @('restart', 'backend')
    Wait-Ready
    & (Join-Path $PSScriptRoot 'invoke-api-loop.ps1') -BaseUrl $baseUrl -ExistingStatePath $statePath
    if ($LASTEXITCODE -ne 0) {
        throw "Docker restart persistence check failed with exit code $LASTEXITCODE"
    }
    $frontend = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173'
    if ($frontend.StatusCode -ne 200) {
        throw "Docker frontend returned HTTP $($frontend.StatusCode)"
    }
    Write-Output "Docker offline acceptance passed. Evidence: $artifactRoot"
}
finally {
    & docker compose --project-name $projectName --project-directory $RepoRoot down --volumes
    $env:RAGOPS_MODEL_EXECUTION_ADAPTER = $previousAdapter
    $env:RAGOPS_MODEL_EXTERNAL_CALLS_ENABLED = $previousExternalCalls
}
