$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$fixtureRoot = Join-Path $repoRoot 'examples\eval-samples'
$validPath = Join-Path $fixtureRoot 'valid-samples.jsonl'
$invalidPath = Join-Path $fixtureRoot 'invalid-samples.jsonl'
$metricPath = Join-Path $fixtureRoot 'metric-cases.json'

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

function Assert-Unique {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Values,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $uniqueCount = @($Values | Sort-Object -Unique).Count
    Assert-Condition ($uniqueCount -eq $Values.Count) "$Name contains duplicate values"
}

$validSamples = @(
    Get-Content -Encoding UTF8 $validPath |
        ForEach-Object { $_ | ConvertFrom-Json }
)
$invalidCases = @(
    Get-Content -Encoding UTF8 $invalidPath |
        ForEach-Object { $_ | ConvertFrom-Json }
)
$metricDocument = Get-Content -Raw -Encoding UTF8 $metricPath | ConvertFrom-Json
$metricCases = @($metricDocument.cases)

Assert-Condition ($validSamples.Count -eq 6) 'valid-samples.jsonl must contain 6 baseline samples'
Assert-Condition ($invalidCases.Count -eq 9) 'invalid-samples.jsonl must contain 9 validation cases'
Assert-Condition ($metricCases.Count -eq 8) 'metric-cases.json must contain 8 metric cases'
Assert-Unique @($validSamples | ForEach-Object { $_.sample_id }) 'sample_id'
Assert-Unique @($invalidCases | ForEach-Object { $_.case_id }) 'invalid case_id'
Assert-Unique @($metricCases | ForEach-Object { $_.case_id }) 'metric case_id'

foreach ($sample in $validSamples) {
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($sample.schema_version)) "$($sample.sample_id): schema_version is required"
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($sample.sample_id)) 'sample_id is required'
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($sample.question)) "$($sample.sample_id): question is required"

    $contexts = @($sample.retrieved_contexts)
    $ranks = @($contexts | ForEach-Object { [int]$_.rank })
    if ($ranks.Count -gt 0) {
        $expectedRanks = @(1..$ranks.Count)
        Assert-Condition ((Compare-Object $ranks $expectedRanks).Count -eq 0) "$($sample.sample_id): ranks must be contiguous and start at 1"
    }

    $chunkIds = @($contexts | ForEach-Object { $_.chunk_id })
    Assert-Unique $chunkIds "$($sample.sample_id) chunk_id"
    foreach ($citation in @($sample.citations)) {
        Assert-Condition ($citation.chunk_id -in $chunkIds) "$($sample.sample_id): citation target '$($citation.chunk_id)' does not exist"
    }
}

foreach ($invalidCase in $invalidCases) {
    Assert-Condition (-not [string]::IsNullOrWhiteSpace($invalidCase.expected_error)) "$($invalidCase.case_id): expected_error is required"
    Assert-Condition ($null -ne $invalidCase.input) "$($invalidCase.case_id): input is required"
}

$rankedMixed = $metricCases | Where-Object { $_.case_id -eq 'ranked-mixed' }
Assert-Condition ($null -ne $rankedMixed) 'ranked-mixed metric case is required'
$idcg = 1 + (1 / [math]::Log(3, 2))
$dcgAt3 = 1 / [math]::Log(3, 2)
$ndcgAt3 = $dcgAt3 / $idcg
$tolerance = [double]$metricDocument.float_tolerance
Assert-Condition ([math]::Abs($ndcgAt3 - [double]$rankedMixed.expected.at_3.ndcg) -le $tolerance) 'ranked-mixed NDCG@3 oracle is inconsistent'
Assert-Condition ([math]::Abs(([double]$rankedMixed.expected.at_4.recall) - 1.0) -le $tolerance) 'ranked-mixed Recall@4 oracle is inconsistent'

$contextPartial = $metricCases | Where-Object { $_.case_id -eq 'context-partial' }
$expectedContextPrecision = (1 + (2 / 3)) / 2
$expectedContextRecall = 2 / 3
Assert-Condition ([math]::Abs($expectedContextPrecision - [double]$contextPartial.expected.context_precision) -le $tolerance) 'context precision oracle is inconsistent'
Assert-Condition ([math]::Abs($expectedContextRecall - [double]$contextPartial.expected.context_recall) -le $tolerance) 'context recall oracle is inconsistent'

$operational = $metricCases | Where-Object { $_.case_id -eq 'latency-and-cost-missing' }
$meanLatency = (100 + 200 + 1000) / 3
Assert-Condition ([math]::Abs($meanLatency - [double]$operational.expected.latency.mean_ms) -le $tolerance) 'latency mean oracle is inconsistent'
Assert-Condition ([math]::Abs((0.01 + 0.03) - [double]$operational.expected.cost.total_amount) -le $tolerance) 'cost oracle is inconsistent'

Write-Output "Fixture validation passed: $($validSamples.Count) valid samples, $($invalidCases.Count) invalid cases, $($metricCases.Count) metric cases."
