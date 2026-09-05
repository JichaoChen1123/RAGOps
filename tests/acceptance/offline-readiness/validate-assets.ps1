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

function Read-JsonLines {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return @(
        Get-Content -Encoding UTF8 $Path |
            Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
            ForEach-Object { $_ | ConvertFrom-Json }
    )
}

$fixtureRoot = Join-Path $RepoRoot 'examples\offline-readiness'
$validPath = Join-Path $fixtureRoot 'valid-v2.jsonl'
$legacyPath = Join-Path $fixtureRoot 'legacy-v1.jsonl'
$invalidPath = Join-Path $fixtureRoot 'invalid-v2.json'
$providerPath = Join-Path $fixtureRoot 'provider-responses.json'
$legacySqlPath = Join-Path $fixtureRoot 'legacy-v1.sql'

foreach ($required in @($validPath, $legacyPath, $invalidPath, $providerPath, $legacySqlPath)) {
    Assert-Condition (Test-Path $required -PathType Leaf) "Required offline fixture is missing: $required"
}

$valid = @(Read-JsonLines $validPath)
$legacy = @(Read-JsonLines $legacyPath)
$invalid = Get-Content -Raw -Encoding UTF8 $invalidPath | ConvertFrom-Json
$provider = Get-Content -Raw -Encoding UTF8 $providerPath | ConvertFrom-Json
$legacySql = Get-Content -Raw -Encoding UTF8 $legacySqlPath

Assert-Condition ($valid.Count -eq 3) 'valid-v2.jsonl must contain exactly 3 synthetic samples'
Assert-Condition ($legacy.Count -eq 1) 'legacy-v1.jsonl must contain exactly 1 synthetic sample'
Assert-Condition (@($invalid.cases).Count -eq 9) 'invalid-v2.json must contain exactly 9 single-row cases'
Assert-Condition (($valid | Select-Object -ExpandProperty sample_id | Sort-Object -Unique).Count -eq $valid.Count) '2.0 sample IDs must be unique'
Assert-Condition (($invalid.cases | Select-Object -ExpandProperty case_id | Sort-Object -Unique).Count -eq @($invalid.cases).Count) 'invalid case IDs must be unique'

foreach ($sample in $valid) {
    Assert-Condition ($sample.schema_version -eq '2.0') "$($sample.sample_id): expected schema_version 2.0"
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($sample.sample_id)) '2.0 sample_id is required'
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($sample.question)) "$($sample.sample_id): question is required"
    $ranks = @($sample.contexts | ForEach-Object { [int]$_.rank } | Sort-Object)
    if ($ranks.Count -gt 0) {
        Assert-Condition ((Compare-Object $ranks @(1..$ranks.Count)).Count -eq 0) "$($sample.sample_id): ranks must be contiguous"
    }
    foreach ($context in @($sample.contexts)) {
        if ($context.origin -eq 'provided') {
            Assert-Condition ($null -eq $context.retrieval_run_id) "$($sample.sample_id): provided context cannot carry retrieval_run_id"
        }
    }
}

Assert-Condition ($legacy[0].schema_version -eq '1.0') 'legacy fixture must use schema_version 1.0'
Assert-Condition ($null -eq $legacy[0].citations[0].supports_claim) 'legacy support judgement must remain unknown'

$requiredInvalidCases = @(
    'schema-null',
    'schema-blank',
    'schema-unknown',
    'question-blank',
    'sample-id-null',
    'mixed-v1-v2-fields',
    'provided-has-retrieval-run',
    'retrieved-missing-retrieval-run',
    'duplicate-rank'
)
Assert-Condition ((Compare-Object @($invalid.cases.case_id | Sort-Object) @($requiredInvalidCases | Sort-Object)).Count -eq 0) 'invalid case coverage changed unexpectedly'

foreach ($name in @(
    'success_full',
    'success_nullable',
    'authentication_401',
    'authorization_403',
    'rate_limited_429',
    'rate_limited_long_retry_after',
    'server_error_500',
    'invalid_json',
    'empty_body',
    'missing_answer',
    'answer_wrong_type'
)) {
    Assert-Condition ($null -ne $provider.$name) "provider response script is missing: $name"
}

$sentinelText = Get-Content -Raw -Encoding UTF8 $validPath
foreach ($sentinel in @(
    'SENTINEL_REFERENCE_7f0b3f',
    'SENTINEL_GOLD_DOCUMENT_7f0b3f',
    'SENTINEL_GOLD_EVIDENCE_7f0b3f',
    'SENTINEL_HISTORICAL_ANSWER_7f0b3f',
    'SENTINEL_METADATA_SECRET_7f0b3f'
)) {
    Assert-Condition ($sentinelText.Contains($sentinel)) "leakage sentinel is missing: $sentinel"
}

foreach ($table in @('datasets', 'dataset_samples', 'evaluation_jobs', 'evaluation_job_samples', 'evaluation_reports')) {
    Assert-Condition ($legacySql.Contains("CREATE TABLE $table")) "legacy SQL is missing table: $table"
}
Assert-Condition ($legacySql.Contains("'confirmed'")) 'legacy SQL must preserve a confirmed review record'

Write-Output 'Offline readiness assets passed: 3 v2 samples, 1 v1 sample, 9 invalid cases, provider scripts, and legacy SQLite seed.'
