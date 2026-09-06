[CmdletBinding()]
param(
    [ValidateSet('Login', 'Status', 'Logout')]
    [string]$Action = 'Login',
    [string]$CodexHome = ''
)

$ErrorActionPreference = 'Stop'

if (-not $CodexHome) {
    $localData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { $HOME }
    $CodexHome = Join-Path $localData 'RAGOps\codex-bridge-home'
}
New-Item -ItemType Directory -Path $CodexHome -Force | Out-Null
$CodexHome = (Resolve-Path -LiteralPath $CodexHome).Path
$dailyCodexHome = [IO.Path]::GetFullPath((Join-Path $HOME '.codex'))
if ($CodexHome -eq $dailyCodexHome) {
    throw 'The bridge CODEX_HOME must be separate from the daily Codex configuration directory.'
}

$codexCommand = Get-Command codex -ErrorAction Stop
$codexExecutable = $codexCommand.Source
if ([IO.Path]::GetExtension($codexExecutable) -eq '.ps1') {
    $cmdShim = [IO.Path]::ChangeExtension($codexExecutable, '.cmd')
    if (Test-Path -LiteralPath $cmdShim) {
        $codexExecutable = $cmdShim
    }
}

$previousCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = $CodexHome
    Write-Host "Bridge Codex home: $CodexHome"
    switch ($Action) {
        'Login' { & $codexExecutable login }
        'Status' { & $codexExecutable login status }
        'Logout' { & $codexExecutable logout }
    }
    if ($Action -eq 'Status' -and $LASTEXITCODE -eq 1) {
        Write-Host 'Bridge-specific Codex login is not configured. Run with -Action Login.'
    }
    elseif ($LASTEXITCODE -ne 0) {
        throw "Codex $($Action.ToLowerInvariant()) exited with code $LASTEXITCODE."
    }
}
finally {
    if ($null -eq $previousCodexHome) {
        Remove-Item Env:CODEX_HOME -ErrorAction SilentlyContinue
    }
    else {
        $env:CODEX_HOME = $previousCodexHome
    }
}
