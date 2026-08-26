import { describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from '../../frontend/src/api/client';

describe('typed API client', () => {
  it('returns isolated mock fixtures for the demo chain', async () => {
    const client = createApiClient({ mode: 'mock', baseUrl: '', mockDelayMs: 0 });
    const tasks = await client.listEvaluationTasks('demo');
    const report = await client.getEvaluationReport('demo', tasks[0].id);
    const diagnosis = await client.getSampleDiagnosis('demo', tasks[0].id, report.samples[0].id);

    expect(report.task.id).toBe('eval-20260826');
    expect(diagnosis.retrievedDocuments.some((document) => document.isExpected)).toBe(true);
    tasks[0].name = 'mutated in test';
    expect((await client.listEvaluationTasks('demo'))[0].name).not.toBe('mutated in test');
  });

  it('calls the configured v1 endpoint and unwraps data envelopes', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ data: [{ id: 'ds-1' }] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: 'http://localhost:8000/api/v1/', fetcher });

    const result = await client.listDatasets('project-a');

    expect(fetcher).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/projects/project-a/datasets',
      expect.objectContaining({ headers: { Accept: 'application/json' } }),
    );
    expect(result).toEqual([{ id: 'ds-1' }]);
  });

  it('surfaces structured backend errors', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ detail: 'dataset unavailable', code: 'DATASET_OFFLINE' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    })) as unknown as typeof fetch;
    const client = createApiClient({ mode: 'api', baseUrl: 'http://localhost:8000/api/v1', fetcher });

    try {
      await client.listDatasets('project-a');
      throw new Error('expected request to fail');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        message: 'dataset unavailable',
        status: 503,
        code: 'DATASET_OFFLINE',
      });
    }
  });
});
