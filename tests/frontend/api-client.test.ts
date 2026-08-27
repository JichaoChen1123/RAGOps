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
  schema_version: '1.0',
  status: 'published',
  sample_count: 6,
  content_sha256: null,
  created_at: '2026-08-27T00:00:00Z',
  published_at: '2026-08-27T00:01:00Z',
};

describe('typed API client', () => {
  it('keeps mutable mock writes isolated inside one client instance', async () => {
    const client = createApiClient({ mode: 'mock', baseUrl: '', mockDelayMs: 0 });
    const tasks = await client.listEvaluationTasks('demo');
    const report = await client.getEvaluationReport('demo', tasks[0].id);
    const diagnosis = await client.getSampleDiagnosis('demo', tasks[0].id, report.samples[0].id);
    const created = await client.createDataset('demo', {
      name: 'Mock import',
      owner: 'tester',
      samples: [{ sampleId: 'sample-1', question: 'What changed?' }],
    });

    expect(report.task.id).toBe('eval-20260826');
    expect(diagnosis.retrievedDocuments.some((document) => document.isExpected)).toBe(true);
    expect((await client.listDatasets('demo'))[0]).toMatchObject({ id: created.id, sampleCount: 1 });
    tasks[0].name = 'mutated in test';
    expect((await client.listEvaluationTasks('demo'))[0].name).not.toBe('mutated in test');
  });

  it('uses the backend resource endpoint and maps snake_case dataset fields', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ items: [rawDataset], total: 1, next_cursor: null })) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: 'http://localhost:8000/api/v1/', fetcher });

    const result = await client.listDatasets('project-a');

    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/datasets',
      expect.objectContaining({ method: 'GET', headers: { Accept: 'application/json' } }),
    );
    expect(result).toEqual([expect.objectContaining({
      id: 'ds-1',
      status: 'ready',
      sampleCount: 6,
      updatedAt: '2026-08-27T00:01:00Z',
    })]);
  });

  it('creates datasets using the WOR-51 write contract', async () => {
    const fetcher = vi.fn(async () => jsonResponse({ ...rawDataset, status: 'draft', published_at: null }, 201)) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: 'http://localhost:8000/api/v1', fetcher });

    await client.createDataset('project-a', {
      name: 'Support golden set',
      description: 'Regression samples',
      owner: 'quality-platform',
      version: 'v1',
      samples: [{ sampleId: 'support-1', question: 'How long are logs kept?' }],
    });

    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/datasets',
      expect.objectContaining({
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Support golden set',
          description: 'Regression samples',
          owner: 'quality-platform',
          version: 'v1',
          schema_version: '1.0',
          samples: [{
            schema_version: '1.0',
            sample_id: 'support-1',
            question: 'How long are logs kept?',
            reference_answer: null,
            tags: [],
          }],
        }),
      }),
    );
  });

  it('updates sample review status through PATCH', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      id: 'result-1',
      sample_id: 'sample-1',
      question: 'Which policy applies?',
      status: 'succeeded',
      answer: 'Policy A',
      retrieval_results: [],
      metric_results: [],
      diagnoses: [{ category: 'citation_gap', severity: 'warning' }],
      review_status: 'confirmed',
      reviewed_at: '2026-08-27T00:02:00Z',
      latency_ms: 20,
      failure_code: null,
      failure_message: null,
    })) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: 'http://localhost:8000/api/v1', fetcher });

    const result = await client.updateSampleReview('project-a', 'job-1', 'result-1', 'confirmed');

    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/evaluation-jobs/job-1/samples/result-1/review',
      expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ review_status: 'confirmed' }) }),
    );
    expect(result).toMatchObject({ id: 'result-1', reviewStatus: 'confirmed', failureType: 'citation_gap' });
  });

  it('surfaces nested structured backend errors', async () => {
    const fetcher = vi.fn(async () => jsonResponse({
      error: { message: 'dataset unavailable', code: 'DATASET_OFFLINE' },
    }, 503)) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: 'http://localhost:8000/api/v1', fetcher });

    await expect(client.listDatasets('project-a')).rejects.toMatchObject({
      message: 'dataset unavailable',
      status: 503,
      code: 'DATASET_OFFLINE',
    } satisfies Partial<ApiError>);
  });
});
