import { describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from '../../frontend/src/api/client';

const jsonResponse = (payload: unknown, status = 200) => new Response(JSON.stringify(payload), {
  status,
  headers: { 'Content-Type': 'application/json' },
});

const rawDataset = {
  id: 'ds-1',
  name: 'Support golden set',
  description: 'Regression samples',
  owner: 'quality-platform',
  version: 'v1',
  schema_version: '2.0',
  status: 'published',
  sample_count: 1,
  content_sha256: 'fixture-hash',
  created_at: '2026-09-05T00:00:00Z',
  published_at: '2026-09-05T00:01:00Z',
};

const executionSnapshot = {
  contract_version: '2.0',
  adapter_id: 'mock',
  provider_id: null,
  prompt: { version: 'prompt-v2', text: 'Use context only.' },
  generation: {
    model: 'mock-ragops-v1', temperature: 0, top_p: 1, max_output_tokens: 512, stop: [], seed: null,
  },
  context_policy: 'dataset_contexts',
  dataset: { id: 'ds-1', version: 'v1', schema_version: '2.0', content_sha256: 'fixture-hash' },
  metric_config: [],
  quality_gate: null,
  external_calls_enabled_at_creation: false,
  created_at: '2026-09-05T00:02:00Z',
  config_version: 'config-v2',
};

const rawJobV2 = {
  id: 'job-1',
  dataset_id: 'ds-1',
  name: 'Offline run',
  schema_version: '2.0',
  status: 'completed',
  outcome: 'succeeded',
  config_version: 'config-v2',
  model_version: 'mock-ragops-v1',
  prompt_version: 'prompt-v2',
  metric_config: [],
  total_count: 1,
  queued_count: 0,
  running_count: 0,
  succeeded_count: 1,
  failed_count: 0,
  progress: 1,
  failure_code: null,
  failure_message: null,
  created_at: '2026-09-05T00:02:00Z',
  started_at: '2026-09-05T00:02:00Z',
  finished_at: '2026-09-05T00:02:01Z',
  adapter_id: 'mock',
  provider_id: null,
  execution_snapshot: executionSnapshot,
  quality_status: 'not_evaluated',
  quality_verdict: 'unknown',
  quality_score: null,
};

const rawSampleV2 = {
  id: 'result-1',
  sample_id: 'sample-1',
  schema_version: '2.0',
  question: 'Which policy applies?',
  labels: {
    reference_answer: 'Policy A',
    gold_document_ids: ['doc-1'],
    gold_evidence_ids: ['ev-1'],
    expected_diagnoses: [],
  },
  reference_answer: 'Policy A',
  historical_answer: 'Historical answer',
  run: {
    run_id: 'run-1',
    status: 'succeeded',
    adapter_id: 'mock',
    provider_id: null,
    requested_model: 'mock-ragops-v1',
    actual_model: 'mock-ragops-v1',
    is_mock: true,
    finish_reason: 'stop',
    answer: '[mock] Context A',
    contexts: [{
      origin: 'provided', rank: 1, rank_before: null, retrieval_run_id: null,
      doc_id: 'doc-1', chunk_id: 'chunk-1', evidence_ids: ['ev-1'], text: 'Context A',
      score: null, relevance_grade: 3, usefulness: true,
    }],
    citations: [{
      citation_id: 'citation-1', claim_id: null, raw: '[1]', target_type: 'document', target_id: 'doc-1',
      resolved: true, supports_claim: null, support_judge_version: null,
    }],
    latency_ms: null,
    usage: null,
    cost: null,
    provider_request_id: null,
    attempt_count: 1,
    attempts: [],
    error: null,
    started_at: '2026-09-05T00:02:00Z',
    finished_at: '2026-09-05T00:02:01Z',
  },
  quality_status: 'not_evaluated',
  metric_results: [
    { metric_name: 'recall_at_5', metric_version: '2.0.0', status: 'not_evaluated', value: null },
    { metric_name: 'citation_resolution_rate', metric_version: '2.0.0', status: 'ok', value: 1 },
    { metric_name: 'citation_support_rate', metric_version: '2.0.0', status: 'not_evaluated', value: null },
  ],
  diagnoses: [],
  review_status: 'pending',
  reviewed_at: null,
};

const rawDiagnosedSampleV2 = {
  ...rawSampleV2,
  diagnoses: [
    {
      rule_id: 'retrieval.missing_evidence', rule_version: '1.0.0', profile_version: 'mvp-default-1.0.0',
      status: 'suspected', severity: 'high', confidence: 0.75,
      reason: 'No observed retrieval candidate contains any gold evidence.',
      evidence: [{ gold_ids: ['ev-1'] }], missing_inputs: [], blocked_by_rule_ids: [], suggestions: [],
    },
    {
      rule_id: 'citation.missing', rule_version: '1.0.0', profile_version: 'mvp-default-1.0.0',
      status: 'confirmed', severity: 'medium', confidence: 1,
      reason: 'The parsed citation list is empty.',
      evidence: [{ citation_count: 0 }], missing_inputs: [], blocked_by_rule_ids: [], suggestions: [],
    },
    {
      rule_id: 'rerank.no_gain_or_regression', rule_version: '1.0.0', profile_version: 'mvp-default-1.0.0',
      status: 'confirmed', severity: 'high', confidence: 0.95,
      reason: 'Gold-aligned evidence fell outside the effective window after reranking.',
      evidence: [{ k: 5 }], missing_inputs: [], blocked_by_rule_ids: [], suggestions: [],
    },
  ],
};

const rawReportV2 = {
  schema_version: '2.0',
  id: 'report-1',
  job_id: 'job-1',
  status: 'completed',
  generated_at: '2026-09-05T00:02:01Z',
  execution_summary: { outcome: 'succeeded', total_count: 1, succeeded_count: 1, failed_count: 0, success_rate: 1 },
  quality_summary: { status: 'not_evaluated', verdict: 'unknown', score: null, evaluated_sample_count: 0 },
  execution_snapshot: executionSnapshot,
  metrics: [{ metric_name: 'execution_success_rate', metric_version: '2.0.0', status: 'ok', value: 1 }],
};

const taskInput = {
  datasetId: 'ds-1',
  adapterId: 'mock' as const,
  prompt: { version: 'prompt-v2', text: 'Use context only.' },
  generation: { model: 'mock-ragops-v1', temperature: 0, topP: 1, maxOutputTokens: 512, stop: [], seed: null },
  contextPolicy: 'dataset_contexts' as const,
  metrics: [],
  qualityGate: null,
};

describe('typed API client 2.0 semantics', () => {
  it('keeps mock writes isolated and refuses unavailable execution without fallback', async () => {
    const client = createApiClient({ mode: 'mock', baseUrl: '', mockDelayMs: 0 });
    const tasks = await client.listEvaluationTasks('demo');
    const report = await client.getEvaluationReport('demo', tasks[0].id);
    const diagnosis = await client.getSampleDiagnosis('demo', tasks[0].id, report.samples[0].id);
    const created = await client.createDataset('demo', { name: 'Mock import', owner: 'tester' });
    const imported = await client.importDatasetSamples('demo', created.id, [{ sampleId: 'sample-1', question: 'What changed?' }]);
    const published = await client.publishDataset('demo', created.id);

    expect(report.qualitySummary).toMatchObject({ status: 'not_evaluated', verdict: 'unknown', score: null });
    expect(diagnosis.contexts.some((context) => context.isExpected)).toBe(true);
    expect(imported.accepted).toBe(1);
    expect(published).toMatchObject({ status: 'ready', sampleCount: 1, schemaVersion: '2.0' });
    tasks[0].name = 'mutated in test';
    expect((await client.listEvaluationTasks('demo'))[0].name).not.toBe('mutated in test');

    await expect(client.createEvaluationTask('demo', { ...taskInput, datasetId: published.id, adapterId: 'openai_compatible' }))
      .rejects.toMatchObject({ code: 'PROVIDER_NOT_CONFIGURED' } satisfies Partial<ApiError>);
  });

  it('maps API datasets without inventing a coverage percentage', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ items: [rawDataset], total: 1, next_cursor: null })) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: 'http://localhost:8000/api/v1/', fetcher });

    const result = await client.listDatasets('project-a');

    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/datasets',
      expect.objectContaining({ method: 'GET', headers: { Accept: 'application/json' } }),
    );
    expect(result[0]).toMatchObject({ id: 'ds-1', status: 'ready', sampleCount: 1, coverage: null, schemaVersion: '2.0' });
  });

  it('preserves 2.0 labels, context provenance, document and chunk IDs during create/import/publish', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/samples:import')) return jsonResponse({ accepted: 1, rejected: 0, dataset: { ...rawDataset, status: 'draft', published_at: null } }, 201);
      return jsonResponse({ ...rawDataset, status: url.endsWith(':publish') ? 'published' : 'draft', published_at: url.endsWith(':publish') ? rawDataset.published_at : null }, url.endsWith('/datasets') ? 201 : 200);
    }) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: 'http://localhost:8000/api/v1', fetcher });
    const sample = {
      sampleId: 'support-1',
      question: 'How long are logs kept?',
      labels: { referenceAnswer: '30 days', goldDocumentIds: ['doc-1'], goldEvidenceIds: ['ev-1'] },
      contexts: [{
        origin: 'provided' as const, rank: 1, retrievalRunId: null, docId: 'doc-1', chunkId: 'chunk-1',
        evidenceIds: ['ev-1'], text: 'Logs are kept for 30 days.', score: null, relevanceGrade: 3, usefulness: true,
      }],
      historicalOutput: null,
      tags: ['synthetic'],
      metadata: { fixture_version: 'v2' },
    };

    const created = await client.createDataset('project-a', { name: 'Support golden set', owner: 'quality-platform' });
    await client.importDatasetSamples('project-a', created.id, [sample]);
    await client.publishDataset('project-a', created.id);

    const createCall = vi.mocked(fetcher).mock.calls[0];
    const importCall = vi.mocked(fetcher).mock.calls[1];
    expect(JSON.parse((createCall[1] as RequestInit).body as string)).toMatchObject({ schema_version: '2.0', samples: [] });
    expect(JSON.parse((importCall[1] as RequestInit).body as string)).toEqual({
      samples: [expect.objectContaining({
        schema_version: '2.0',
        sample_id: 'support-1',
        labels: expect.objectContaining({ reference_answer: '30 days', gold_document_ids: ['doc-1'] }),
        contexts: [expect.objectContaining({ origin: 'provided', retrieval_run_id: null, doc_id: 'doc-1', chunk_id: 'chunk-1', score: null })],
        historical_output: null,
      })],
    });
    expect(vi.mocked(fetcher).mock.calls[2][0]).toBe('http://localhost:8000/api/v1/datasets/ds-1:publish');
  });

  it('shows API frontend + mock backend + configured-unverified provider as independent axes', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      schema_version: '2.0',
      backend_execution_adapter: 'mock',
      external_calls_enabled: false,
      execution_available: true,
      active_adapter: {
        adapter_id: 'mock', is_mock: true,
        capabilities: { external_network: false, supports_seed: true, supports_stop: true, reports_usage: false, reports_request_id: false },
      },
      providers: [{
        provider_id: 'openai_compatible', configuration_status: 'configured_unverified', base_url_configured: true,
        credential_configured: true, default_model_configured: true, last_verified_at: null, verification_message: null,
      }],
    })) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: '/api/v1', fetcher });

    const status = await client.getModelExecutionStatus();

    expect(status).toMatchObject({ source: 'api', backendExecutionAdapter: 'mock', externalCallsEnabled: false });
    expect(status.providers[0]).toMatchObject({ configurationStatus: 'configured_unverified', lastVerifiedAt: null });
  });

  it('keeps successful execution separate from unknown quality and preserves citation semantics', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/report')) return jsonResponse(rawReportV2);
      if (url.endsWith('/samples')) return jsonResponse({ items: [rawSampleV2], total: 1 });
      return jsonResponse(rawJobV2);
    }) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: '/api/v1', fetcher });

    const report = await client.getEvaluationReport('project-a', 'job-1');
    const diagnosis = await client.getSampleDiagnosis('project-a', 'job-1', 'sample-1');

    expect(report.task).toMatchObject({ outcome: 'succeeded', qualityStatus: 'not_evaluated', qualityVerdict: 'unknown', qualityScore: null });
    expect(report).toMatchObject({ verdict: 'undetermined', isSimulated: true });
    expect(report.verdictReason).toMatch(/不能据执行成功推断答案质量/);
    expect(diagnosis).toMatchObject({
      expectedAnswer: 'Policy A', historicalAnswer: 'Historical answer', generatedAnswer: '[mock] Context A',
      qualityStatus: 'not_evaluated',
    });
    expect(diagnosis.contexts[0]).toMatchObject({ origin: 'provided', retrievalRunId: null, docId: 'doc-1', chunkId: 'chunk-1', score: null });
    expect(diagnosis.citations[0]).toMatchObject({ resolved: true, supportsClaim: null });
    expect(diagnosis.metrics.find((metric) => metric.key === 'citation_support_rate')).toMatchObject({ status: 'not_evaluated', value: null });
    expect(diagnosis.run).toMatchObject({ latencyMs: null, usage: null, cost: null });
  });

  it('maps snake_case diagnosis rules into sample details and primary-rule report buckets', async () => {
    const legacyDiagnosedSample = {
      ...rawSampleV2,
      id: 'result-legacy-diagnosis',
      sample_id: 'sample-legacy-diagnosis',
      diagnoses: [{ label: 'legacy.diagnosis', severity: 'medium', reason: 'Legacy diagnosis field.' }],
    };
    const undiagnosedSample = {
      ...rawSampleV2,
      id: 'result-without-diagnosis',
      sample_id: 'sample-without-diagnosis',
      diagnoses: [],
    };
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/report')) return jsonResponse({
        ...rawReportV2,
        execution_summary: { outcome: 'succeeded', total_count: 3, succeeded_count: 3, failed_count: 0, success_rate: 1 },
      });
      if (url.endsWith('/samples')) return jsonResponse({
        items: [rawDiagnosedSampleV2, legacyDiagnosedSample, undiagnosedSample], total: 3,
      });
      return jsonResponse({ ...rawJobV2, total_count: 3, succeeded_count: 3 });
    }) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: '/api/v1', fetcher });

    const report = await client.getEvaluationReport('project-a', 'job-1');
    const diagnosis = await client.getSampleDiagnosis('project-a', 'job-1', 'sample-1');
    const legacyDiagnosis = await client.getSampleDiagnosis('project-a', 'job-1', 'sample-legacy-diagnosis');
    const missingDiagnosis = await client.getSampleDiagnosis('project-a', 'job-1', 'sample-without-diagnosis');

    expect(diagnosis.primaryDiagnosis.label).toBe('retrieval.missing_evidence');
    expect(diagnosis.secondaryDiagnoses.map((item) => item.label)).toEqual([
      'citation.missing',
      'rerank.no_gain_or_regression',
    ]);
    expect(report.samples.map((sample) => sample.failureType)).toEqual([
      'retrieval.missing_evidence',
      'legacy.diagnosis',
      'unclassified',
    ]);
    expect(report.failures.map(({ key, label, count }) => ({ key, label, count }))).toEqual([
      { key: 'retrieval.missing_evidence', label: 'retrieval.missing_evidence', count: 1 },
      { key: 'legacy.diagnosis', label: 'legacy.diagnosis', count: 1 },
    ]);
    expect(legacyDiagnosis.primaryDiagnosis.label).toBe('legacy.diagnosis');
    expect(missingDiagnosis).toMatchObject({
      primaryDiagnosis: { label: '未生成诊断' },
      secondaryDiagnoses: [],
    });
  });

  it('does not reinterpret legacy model, context source, simulation or quality fields', async () => {
    const legacyJob = {
      ...rawJobV2,
      schema_version: undefined,
      execution_snapshot: null,
      adapter_id: undefined,
      model_version: 'looks-like-a-real-model',
      quality_status: undefined,
      quality_verdict: undefined,
    };
    const legacySample = {
      id: 'legacy-result', sample_id: 'legacy-sample', question: 'Legacy question', status: 'succeeded', answer: 'Legacy run answer',
      reference_answer: 'Legacy reference', retrieval_results: [{ rank: 1, doc_id: 'legacy-doc', chunk_id: 'legacy-chunk', text: 'Legacy context', score: 0.9 }],
      metric_results: [{ metric_name: 'citation_hit_rate', status: 'legacy', value: 0.8 }], diagnoses: [],
      review_status: 'pending', reviewed_at: null, latency_ms: null,
    };
    const legacyReport = {
      id: 'legacy-report', job_id: 'job-1', status: 'completed', outcome: 'succeeded', generated_at: '2026-01-01T00:00:00Z',
      summary: { total_count: 1, succeeded_count: 1, failed_count: 0 }, metrics: [],
    };
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/report')) return jsonResponse(legacyReport);
      if (url.endsWith('/samples')) return jsonResponse({ items: [legacySample], total: 1 });
      return jsonResponse(legacyJob);
    }) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: '/api/v1', fetcher });

    const report = await client.getEvaluationReport('project-a', 'job-1');
    const diagnosis = await client.getSampleDiagnosis('project-a', 'job-1', 'legacy-sample');

    expect(report.task).toMatchObject({ modelVersion: null, isMock: null, qualityStatus: 'legacy_unknown', qualityScore: null });
    expect(report).toMatchObject({ verdict: 'undetermined', isSimulated: null });
    expect(diagnosis).toMatchObject({ expectedAnswer: 'Legacy reference', generatedAnswer: 'Legacy run answer' });
    expect(diagnosis.contexts[0]).toMatchObject({ origin: 'legacy_unknown', docId: 'legacy-doc', chunkId: 'legacy-chunk' });
  });

  it('submits the frozen 2.0 task shape without legacy execution fields', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ ...rawJobV2, status: 'queued', outcome: null, progress: 0 })) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: '/api/v1', fetcher });

    await client.createEvaluationTask('project-a', taskInput);

    const body = JSON.parse((vi.mocked(fetcher).mock.calls[0][1] as RequestInit).body as string);
    expect(body).toEqual(expect.objectContaining({
      schema_version: '2.0', dataset_id: 'ds-1', metrics: [], quality_gate: null,
      execution: expect.objectContaining({ adapter_id: 'mock', context_policy: 'dataset_contexts' }),
    }));
    expect(body).not.toHaveProperty('model_version');
    expect(body).not.toHaveProperty('prompt_version');
  });

  it('surfaces structured errors and empty responses without fixture fallback', async () => {
    const errorFetcher = vi.fn(async () => jsonResponse({ error: { message: 'provider is not configured', code: 'PROVIDER_NOT_CONFIGURED' } }, 409)) as unknown as typeof fetch;
    const errorClient = createApiClient({ mode: 'api', baseUrl: '/api/v1', fetcher: errorFetcher });
    await expect(errorClient.createEvaluationTask('project-a', taskInput)).rejects.toMatchObject({
      message: 'provider is not configured', status: 409, code: 'PROVIDER_NOT_CONFIGURED',
    } satisfies Partial<ApiError>);

    const emptyFetcher = vi.fn(async () => new Response('', { status: 200 })) as unknown as typeof fetch;
    const emptyClient = createApiClient({ mode: 'api', baseUrl: '/api/v1', fetcher: emptyFetcher });
    await expect(emptyClient.listDatasets('project-a')).rejects.toMatchObject({ code: 'EMPTY_RESPONSE' } satisfies Partial<ApiError>);
  });

  it('updates sample review status through PATCH', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ ...rawSampleV2, review_status: 'confirmed' })) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: '/api/v1', fetcher });

    const result = await client.updateSampleReview('project-a', 'job-1', 'result-1', 'confirmed');

    expect(fetcher).toHaveBeenCalledWith(
      '/api/v1/evaluation-jobs/job-1/samples/result-1/review',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ review_status: 'confirmed' }) }),
    );
    expect(result).toMatchObject({ id: 'result-1', reviewStatus: 'confirmed', qualityStatus: 'not_evaluated' });
  });
});
