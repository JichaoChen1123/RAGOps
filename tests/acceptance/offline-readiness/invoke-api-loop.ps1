[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [string]$StatePath,

    [string]$ExistingStatePath,

    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')

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

function Invoke-Json {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [object]$Body,

        [hashtable]$Headers
    )

    $arguments = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
        ContentType = 'application/json; charset=utf-8'
    }
    if ($null -ne $Body) {
        $arguments.Body = $Body | ConvertTo-Json -Depth 20 -Compress
    }
    return Invoke-RestMethod @arguments
}

function Wait-JobTerminal {
    param(
        [Parameter(Mandatory = $true)]
        [string]$JobId
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $job = Invoke-Json -Method Get -Uri "$BaseUrl/api/v1/evaluation-jobs/$JobId"
        if ($job.status -in @('completed', 'failed', 'cancelled')) {
            return $job
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    throw "Evaluation job did not reach a terminal state within $TimeoutSeconds seconds: $JobId"
}

$live = Invoke-Json -Method Get -Uri "$BaseUrl/health/live"
$ready = Invoke-Json -Method Get -Uri "$BaseUrl/health/ready"
$executionStatus = Invoke-Json -Method Get -Uri "$BaseUrl/api/v1/model-execution/status"
Assert-Condition ($live.status -eq 'ok') 'Liveness check did not return ok'
Assert-Condition ($ready.status -eq 'ready') 'Readiness check did not return ready'
Assert-Condition ($executionStatus.backend_execution_adapter -eq 'mock') 'Acceptance loop requires backend mock adapter'
Assert-Condition (-not $executionStatus.external_calls_enabled) 'External model calls must be disabled'

if (-not [string]::IsNullOrWhiteSpace($ExistingStatePath)) {
    $state = Get-Content -Raw -Encoding UTF8 (Resolve-Path $ExistingStatePath) | ConvertFrom-Json
    $job = Wait-JobTerminal -JobId $state.job_id
}
else {
    $sample = @{
        schema_version = '2.0'
        sample_id = 'api-loop-sample-001'
        question = '离线 API 闭环是否调用真实模型？'
        labels = @{
            reference_answer = '不会。'
            gold_document_ids = @('doc-offline')
            gold_evidence_ids = @('ev-offline')
            expected_diagnoses = @()
        }
        contexts = @(
            @{
                origin = 'provided'
                rank = 1
                rank_before = $null
                retrieval_run_id = $null
                doc_id = 'doc-offline'
                chunk_id = 'chunk-offline'
                evidence_ids = @('ev-offline')
                text = '离线 API 闭环只使用模拟适配器。'
                score = $null
                relevance_grade = 3
                usefulness = $true
            }
        )
        historical_output = $null
        tags = @('synthetic', 'stage3')
        metadata = @{}
    }
    $dataset = Invoke-Json -Method Post -Uri "$BaseUrl/api/v1/datasets" -Body @{
        name = "offline-api-loop-$([Guid]::NewGuid())"
        description = 'Synthetic Stage 3 API loop.'
        owner = 'qa'
        version = 'v2'
        schema_version = '2.0'
    }
    $imported = Invoke-Json -Method Post -Uri "$BaseUrl/api/v1/datasets/$($dataset.id)/samples:import" -Body @{ samples = @($sample) }
    Assert-Condition ($imported.accepted -eq 1) 'Exactly one sample must be imported'
    $published = Invoke-Json -Method Post -Uri "$BaseUrl/api/v1/datasets/$($dataset.id):publish"
    Assert-Condition ($published.status -eq 'published') 'Dataset was not published'
    Assert-Condition ($published.content_sha256.Length -eq 64) 'Dataset hash is not SHA-256'

    $created = Invoke-Json -Method Post -Uri "$BaseUrl/api/v1/evaluation-jobs" -Headers @{
        'Idempotency-Key' = "offline-api-loop-$([Guid]::NewGuid())"
    } -Body @{
        schema_version = '2.0'
        dataset_id = $dataset.id
        name = 'offline API loop'
        execution = @{
            adapter_id = 'mock'
            prompt = @{ version = 'offline-stage3-v1'; text = '仅依据上下文回答。' }
            generation = @{
                model = 'mock-ragops-v1'
                temperature = 0.0
                top_p = 1.0
                max_output_tokens = 256
                stop = @()
                seed = $null
            }
            context_policy = 'dataset_contexts'
        }
        metrics = @()
        quality_gate = $null
    }
    $job = Wait-JobTerminal -JobId $created.id
    $state = @{
        dataset_id = $dataset.id
        content_sha256 = $published.content_sha256
        job_id = $job.id
    }
}

$samples = Invoke-Json -Method Get -Uri "$BaseUrl/api/v1/evaluation-jobs/$($state.job_id)/samples"
$report = Invoke-Json -Method Get -Uri "$BaseUrl/api/v1/evaluation-jobs/$($state.job_id)/report"
$export = Invoke-Json -Method Get -Uri "$BaseUrl/api/v1/evaluation-jobs/$($state.job_id)/report/export"
Assert-Condition ($job.status -eq 'completed') 'Mock job must complete'
Assert-Condition ($job.outcome -eq 'succeeded') 'Mock job execution must succeed'
Assert-Condition ($job.quality_status -eq 'not_evaluated') 'Execution success must not imply evaluated quality'
Assert-Condition ($job.quality_verdict -eq 'unknown') 'Execution success must not imply quality passed'
Assert-Condition ($null -eq $job.quality_score) 'Unknown quality score must remain null'
Assert-Condition ($samples.total -eq 1) 'Expected one persisted sample result'
Assert-Condition ($samples.items[0].run.is_mock) 'Persisted run must be marked mock'
Assert-Condition ($report.execution_summary.success_rate -eq 1.0) 'Execution success rate must be 1.0'
Assert-Condition ($report.quality_summary.status -eq 'not_evaluated') 'Report quality must remain not evaluated'
Assert-Condition ($null -eq $report.quality_summary.score) 'Report quality score must remain null'
Assert-Condition ($export.samples.Count -eq 1) 'Export must include the complete sample result'

if (-not [string]::IsNullOrWhiteSpace($StatePath)) {
    $resolvedState = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($StatePath)
    $state | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $resolvedState
}

[PSCustomObject]@{
    result = 'passed'
    dataset_id = $state.dataset_id
    job_id = $state.job_id
    execution = $job.outcome
    quality = $job.quality_status
    real_provider_validation = 'not_executed_by_scope'
} | ConvertTo-Json -Depth 5
