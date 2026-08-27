import { datasets, diagnosis, evaluationTasks, projectOverview, report } from './fixtures';
import type {
  ApiClient,
  Dataset,
  EvaluationReport,
  EvaluationTask,
  ProjectOverview,
  SampleDiagnosis,
} from '../types';

export type ApiMode = 'mock' | 'api';

export interface ApiClientConfig {
  mode: ApiMode;
  baseUrl: string;
  fetcher?: typeof fetch;
  mockDelayMs?: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const clone = <T,>(value: T): T => structuredClone(value);

class MockApiClient implements ApiClient {
  constructor(private readonly delayMs: number) {}

  private async respond<T>(value: T): Promise<T> {
    if (this.delayMs > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, this.delayMs));
    }
    return clone(value);
  }

  getProjectOverview(_projectId: string): Promise<ProjectOverview> {
    return this.respond(projectOverview);
  }

  listDatasets(_projectId: string): Promise<Dataset[]> {
    return this.respond(datasets);
  }

  listEvaluationTasks(_projectId: string): Promise<EvaluationTask[]> {
    return this.respond(evaluationTasks);
  }

  getEvaluationReport(_projectId: string, taskId: string): Promise<EvaluationReport> {
    if (taskId !== report.task.id) {
      return Promise.reject(new ApiError('找不到指定评测报告', 404, 'REPORT_NOT_FOUND'));
    }
    return this.respond(report);
  }

  getSampleDiagnosis(_projectId: string, taskId: string, sampleId: string): Promise<SampleDiagnosis> {
    if (taskId !== diagnosis.taskId || sampleId !== diagnosis.id) {
      return Promise.reject(new ApiError('找不到指定样本诊断', 404, 'DIAGNOSIS_NOT_FOUND'));
    }
    return this.respond(diagnosis);
  }
}

class HttpApiClient implements ApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string, private readonly fetcher: typeof fetch) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  private async request<T>(path: string): Promise<T> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10_000);

    try {
      const response = await this.fetcher(`${this.baseUrl}${path}`, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      const payload = (await response.json().catch(() => null)) as
        | T
        | { data: T }
        | { detail?: string; message?: string; code?: string }
        | null;

      if (!response.ok) {
        const errorPayload = payload as { detail?: string; message?: string; code?: string } | null;
        throw new ApiError(
          errorPayload?.detail ?? errorPayload?.message ?? `请求失败（HTTP ${response.status}）`,
          response.status,
          errorPayload?.code,
        );
      }
      if (payload === null) {
        throw new ApiError('后端返回了空响应', response.status, 'EMPTY_RESPONSE');
      }
      if (typeof payload === 'object' && 'data' in payload) {
        return payload.data;
      }
      return payload as T;
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError('请求超时，请稍后重试', undefined, 'TIMEOUT');
      }
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  getProjectOverview(projectId: string): Promise<ProjectOverview> {
    return this.request(`/projects/${projectId}/overview`);
  }

  listDatasets(projectId: string): Promise<Dataset[]> {
    return this.request(`/projects/${projectId}/datasets`);
  }

  listEvaluationTasks(projectId: string): Promise<EvaluationTask[]> {
    return this.request(`/projects/${projectId}/evaluations`);
  }

  getEvaluationReport(projectId: string, taskId: string): Promise<EvaluationReport> {
    return this.request(`/projects/${projectId}/evaluations/${taskId}/report`);
  }

  getSampleDiagnosis(projectId: string, taskId: string, sampleId: string): Promise<SampleDiagnosis> {
    return this.request(`/projects/${projectId}/evaluations/${taskId}/samples/${sampleId}`);
  }
}

export function createApiClient(config: ApiClientConfig): ApiClient {
  if (config.mode === 'mock') {
    return new MockApiClient(config.mockDelayMs ?? 180);
  }
  return new HttpApiClient(config.baseUrl, config.fetcher ?? window.fetch.bind(window));
}

const configuredMode = import.meta.env.VITE_API_MODE === 'api' ? 'api' : 'mock';

export const apiMode: ApiMode = configuredMode;
export const apiClient = createApiClient({
  mode: configuredMode,
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
});
