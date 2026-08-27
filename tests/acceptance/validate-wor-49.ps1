[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..'))
)

$ErrorActionPreference = 'Stop'

function Assert-Condition {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

$manifestPath = Join-Path $RepoRoot 'tests\acceptance\wor-49-visible-interactions.json'
$acceptancePath = Join-Path $RepoRoot 'docs\qa\wor-49-visible-interactions.md'
$readmePath = Join-Path $RepoRoot 'README.md'

Assert-Condition (Test-Path $manifestPath -PathType Leaf) 'WOR-49 interaction manifest is missing'
Assert-Condition (Test-Path $acceptancePath -PathType Leaf) 'WOR-49 acceptance document is missing'
Assert-Condition (Test-Path $readmePath -PathType Leaf) 'README.md is missing'

$manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
$cases = @($manifest.interactions)
$expectedIds = @(
    'W49-UI-001', 'W49-UI-002', 'W49-UI-003', 'W49-UI-004', 'W49-UI-005',
    'W49-UI-006', 'W49-UI-007', 'W49-UI-008', 'W49-UI-009', 'W49-UI-010',
    'W49-UI-011', 'W49-UI-012', 'W49-UI-013', 'W49-UI-014', 'W49-UI-015'
)
$writeOperations = @('createDataset', 'importDatasetSamples', 'createEvaluation', 'updateSampleReview')

Assert-Condition ($manifest.schema_version -eq '1.0') 'Unexpected WOR-49 manifest schema_version'
Assert-Condition ($manifest.issue -eq 'WOR-49') 'Manifest must be traceable to WOR-49'
Assert-Condition ($manifest.policy.silent_noop_allowed -eq $false) 'Silent no-op behavior must be forbidden'
Assert-Condition ($manifest.policy.api_silent_mock_fallback_allowed -eq $false) 'Silent API-to-mock fallback must be forbidden'
Assert-Condition ($cases.Count -eq $expectedIds.Count) "Expected $($expectedIds.Count) interaction cases, found $($cases.Count)"

$ids = @($cases | ForEach-Object { $_.id })
Assert-Condition ((@($ids | Sort-Object -Unique)).Count -eq $ids.Count) 'Interaction IDs must be unique'
Assert-Condition ((Compare-Object ($expectedIds | Sort-Object) ($ids | Sort-Object)).Count -eq 0) 'Required interaction IDs changed or are missing'

foreach ($case in $cases) {
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($case.surface)) "$($case.id): surface is required"
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($case.control)) "$($case.id): control is required"
    Assert-Condition ($case.priority -in @('P0', 'P1')) "$($case.id): priority must be P0 or P1"
    Assert-Condition (@($case.modes).Count -eq 2) "$($case.id): both mock and api modes are required"
    Assert-Condition ('mock' -in @($case.modes)) "$($case.id): mock mode is missing"
    Assert-Condition ('api' -in @($case.modes)) "$($case.id): api mode is missing"
    Assert-Condition (@($case.steps).Count -gt 0) "$($case.id): at least one operation step is required"
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($case.expected_by_mode.mock)) "$($case.id): mock expectation is required"
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($case.expected_by_mode.api)) "$($case.id): api expectation is required"
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($case.automation_target)) "$($case.id): automation target is required"

}

foreach ($operation in $writeOperations) {
    Assert-Condition ($operation -in @($cases | ForEach-Object { $_.api_operation })) "Missing required write operation: $operation"
}

$acceptance = Get-Content -Raw -Encoding UTF8 $acceptancePath
$readme = Get-Content -Raw -Encoding UTF8 $readmePath
foreach ($id in $expectedIds) {
    Assert-Condition ($acceptance.Contains($id)) "Acceptance document does not reference $id"
}

foreach ($heading in @('### Mock ', '### API ', 'No silent fallback')) {
    Assert-Condition ($readme.Contains($heading)) "README mode boundary is missing: $heading"
}

Write-Output "WOR-49 contract validation passed: $($cases.Count) interactions, both modes covered, required writes mapped."
