[CmdletBinding()]
param(
    [switch]$Docker,
    [ValidateRange(1, 65535)]
    [int]$Port = 8765,
    [ValidateRange(5, 600)]
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repoRoot '.env'

if (-not $env:RAGOPS_CODEX_BRIDGE_TOKEN -and (Test-Path -LiteralPath $envFile)) {
    $tokenLine = Get-Content -LiteralPath $envFile -Encoding UTF8 |
        Where-Object { $_ -match '^RAGOPS_CODEX_BRIDGE_TOKEN=' } |
        Select-Object -Last 1
    if ($tokenLine) {
        $env:RAGOPS_CODEX_BRIDGE_TOKEN = ($tokenLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
    }
}

if (-not $env:RAGOPS_CODEX_BRIDGE_TOKEN -or $env:RAGOPS_CODEX_BRIDGE_TOKEN.Length -lt 32) {
    throw 'Set RAGOPS_CODEX_BRIDGE_TOKEN to a random value of at least 32 characters in .env.'
}

$bindHost = if ($Docker) { '0.0.0.0' } else { '127.0.0.1' }
$arguments = @(
    'run', 'ragops', 'codex-bridge',
    '--host', $bindHost,
    '--port', $Port,
    '--timeout-seconds', $TimeoutSeconds
)
if ($Docker) {
    $arguments += '--allow-non-loopback'
    Write-Host 'Docker bridge mode enabled. Keep Windows Firewall enabled; every model endpoint requires the bridge token.'
}

Push-Location (Join-Path $repoRoot 'backend')
try {
    & uv @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Codex bridge exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
