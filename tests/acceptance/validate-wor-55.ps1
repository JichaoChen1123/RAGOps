[CmdletBinding()]
param(
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepoRoot = (Resolve-Path (Join-Path $scriptDirectory '..\..')).Path
}
else {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
}

function Assert-Contains {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Content,

        [Parameter(Mandatory = $true)]
        [string]$Needle,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Content.Contains($Needle)) {
        throw $Message
    }
}

function Read-Utf8File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    $path = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path $path -PathType Leaf)) {
        throw "Required file is missing: $RelativePath"
    }

    return Get-Content -Raw -Encoding UTF8 $path
}

$readme = Read-Utf8File 'README.md'
$overview = Read-Utf8File 'frontend\src\pages\OverviewPage.tsx'
$workspaceShell = Read-Utf8File 'frontend\src\components\WorkspaceShell.tsx'
$styles = Read-Utf8File 'frontend\src\styles.css'
$workflow = Read-Utf8File '.github\workflows\ci.yml'
$package = (Read-Utf8File 'frontend\package.json') | ConvertFrom-Json

$readmeContracts = @(
    '# RAGOps',
    'React',
    'TypeScript',
    'FastAPI',
    'Mock UI',
    'VITE_API_MODE=mock',
    'VITE_API_MODE=api',
    'No silent fallback',
    'npm --prefix frontend run dev',
    'npm --prefix frontend run typecheck',
    'npm --prefix frontend test',
    'npm --prefix frontend run build',
    'LLM provider',
    'Embedding/Rerank',
    'SQLite',
    'Recall@K',
    'Vitest',
    'Pytest',
    'E2E',
    'Docker'
)

foreach ($contract in $readmeContracts) {
    Assert-Contains $readme $contract "README contract is missing: $contract"
}

foreach ($step in @('Dataset', 'Evaluation Job', 'Metrics', 'Failure Diagnosis', 'Report', 'Review')) {
    Assert-Contains $overview $step "Overview pipeline step is missing: $step"
}

foreach ($capability in @(
    'MOCK FIXTURE',
    'Dataset schema',
    'Adapter',
    'Prompt',
    'Generation config',
    'not evaluated',
    'DIAGNOSIS RULES',
    'VERSION TRACE',
    'DELIVERY GATE'
)) {
    Assert-Contains $overview $capability "Overview capability is missing: $capability"
}

Assert-Contains $workspaceShell 'nav-readonly' 'Workspace must retain the working read-only configuration entry.'
Assert-Contains $workspaceShell 'READ' 'Workspace must disclose the read-only configuration state.'
Assert-Contains $workspaceShell 'LIVE' 'Workspace must retain the working quality-trends entry.'

# Unreleased navigation must be absent rather than presented as a disabled or
# roadmap action. This verifies the current single-project workbench behavior
# without treating a non-functional click target as a valid interaction.
foreach ($unavailableNavigation in @('nav-coming-soon', 'nav-disabled', '其他项目', '版本对比', '项目设置')) {
    if ($workspaceShell.Contains($unavailableNavigation)) {
        throw "Unavailable workspace navigation must be hidden: $unavailableNavigation"
    }
}

foreach ($styleContract in @(
    '.sidebar nav a:hover',
    '.sidebar nav a.active',
    '.project-identity',
    'button:disabled'
)) {
    Assert-Contains $styles $styleContract "Navigation style contract is missing: $styleContract"
}

if ($package.scripts.typecheck -ne 'tsc --noEmit') {
    throw 'frontend typecheck script changed unexpectedly'
}
if ($package.scripts.test -ne 'vitest run') {
    throw 'frontend test script changed unexpectedly'
}
if (-not $package.scripts.build.Contains('vite build')) {
    throw 'frontend build script no longer runs Vite build'
}

foreach ($gate in @(
    'npm --prefix frontend run typecheck',
    'npm --prefix frontend test',
    'npm --prefix frontend run build',
    './tests/acceptance/validate-wor-55.ps1'
)) {
    Assert-Contains $workflow $gate "CI gate is missing: $gate"
}

Write-Output 'WOR-55 contract validation passed: README, RAGOps pipeline, navigation states, scripts, and CI gate are present.'
