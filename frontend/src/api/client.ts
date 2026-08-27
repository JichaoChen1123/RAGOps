import { datasets, diagnosis, evaluationTasks, projectOverview, report } from './fixtures';
import type {
  ApiClient,
  Dataset,
  DatasetCreateInput,
  EvaluationReport,
  EvaluationTask,
  EvaluationTaskCreateInput,
  FailureBucket,
  MetricValue,
  ProjectOverview,
  ReportExport,
  SampleDiagnosis,
  SampleReviewStatus,
  SampleSummary,
  Severity,
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

interface RawDataset {
  id: string;
  name: string;
  description: string | null;
  owner: string;
  version: string;
  status: 'draft' | 'published';
  sample_count: number;
  created_at: string;
  published_at: string | null;
}

interface RawDatasetList {
  items: RawDataset[];
  total: number;
  next_cursor: string | null;
}

interface RawEvaluationJob {
  id: string;
  dataset_id: string;
  name: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  outcome: 'succeeded' | 'partial_failed' | 'failed' | null;
  config_version: string;
  model_version: string;
  prompt_version: string;
  total_count: number;
  failed_count: number;
  progress: number;
  created_at: string;
  finished_at: string | null;
}

interface RawEvaluationJobList {
  items: RawEvaluationJob[];
  total: number;
}

interface RawEvaluationSample {
  id: string;
  sample_id: string;
  question: string;
  status: string;
  answer: string | null;
  retrieval_results: Array<Record<string, unknown>>;
  metric_results: Array<Record<string, unknown>>;
  diagnoses: Array<Record<string, unknown>>;
  review_status: SampleReviewStatus;
  reviewed_at: string | null;
  latency_ms: number | null;
}

interface RawEvaluationSampleList {
  items: RawEvaluationSample[];
  total: number;
}

interface RawEvaluationReport {
  id: string;
  job_id: string;
  status: RawEvaluationJob['status'];
  outcome: Exclude<RawEvaluationJob['outcome'], null>;
  generated_at: string;
  summary: Record<string, number>;
  metrics: Array<Record<string, unknown>>;
}

interface RawReportExport {
  schema_version: '1.0';
  exported_at: string;
  report: RawEvaluationReport;
  samples: RawEvaluationSample[];
}

interface StructuredErrorPayload {
  detail?: string | unknown[];
  message?: string;
  code?: string;
  error?: {
    message?: string;
    code?: string;
  };
}

const clone = <T,>(value: T): T => structuredClone(value);
const now = () => new Date().toISOString();

function recordString(record: Record<string, unknown> | undefined, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record?.[key];
    if (typeof value === 'string' && value.length > 0) return value;
  }
  return undefined;
}

function recordNumber(record: Record<string, unknown> | undefined, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = record?.[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

function normalizeSeverity(value?: string): Severity {
  if (value === 'critical' || value === 'warning' || value === 'healthy') return value;
  return 'unknown';
}

function mapDataset(raw: RawDataset): Dataset {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description ?? '',
    sampleCount: raw.sample_count,
    status: raw.status === 'published' ? 'ready' : 'draft',
    version: raw.version,
    coverage: raw.status === 'published' ? 100 : raw.sample_count > 0 ? 50 : 0,
    updatedAt: raw.published_at ?? raw.created_at,
    owner: raw.owner,
  };
}

function mapTask(raw: RawEvaluationJob, datasetName = raw.dataset_id): EvaluationTask {
  return {
    id: raw.id,
    name: raw.name,
    datasetId: raw.dataset_id,
    datasetName,
    status: raw.status === 'cancelled' ? 'failed' : raw.status,
    progress: Math.round(raw.progress * 100),
    createdAt: raw.created_at,
    completedAt: raw.finished_at ?? undefined,
    modelVersion: raw.model_version,
    promptVersion: raw.prompt_version,
    totalSamples: raw.total_count,
    failedSamples: raw.failed_count,
    score: raw.outcome === 'succeeded' ? 100 : raw.outcome === 'failed' ? 0 : undefined,
  };
}

function findMetric(records: Array<Record<string, unknown>>, name: string): number | null {
  const record = records.find((candidate) => recordString(candidate, 'metric_name', 'name', 'key') === name);
  return recordNumber(record, 'value', 'score');
}

function mapMetric(record: Record<string, unknown>, index: number): MetricValue {
  const key = recordString(record, 'metric_name', 'name', 'key') ?? `metric-${index + 1}`;
  return {
    key,
    label: key.replaceAll('_', ' '),
    value: recordNumber(record, 'value', 'score'),
  };
}

function mapSample(raw: RawEvaluationSample): SampleSummary {
  const diagnosisRecord = raw.diagnoses[0];
  return {
    id: raw.id,
    question: raw.question,
    failureType: recordString(diagnosisRecord, 'category', 'label', 'rule', 'code') ?? 'unclassified',
    severity: normalizeSeverity(recordString(diagnosisRecord, 'severity')),
    recallAt5: findMetric(raw.metric_results, 'recall_at_5'),
    faithfulness: findMetric(raw.metric_results, 'faithfulness'),
    citationHitRate: findMetric(raw.metric_results, 'citation_hit_rate'),
    latencyMs: raw.latency_ms ?? 0,
    reviewStatus: raw.review_status,
  };
}

function failureBuckets(samples: SampleSummary[]): FailureBucket[] {
  const grouped = new Map<string, FailureBucket>();
  for (const sample of samples) {
    const current = grouped.get(sample.failureType);
    if (current) current.count += 1;
    else {
      grouped.set(sample.failureType, {
        key: sample.failureType,
        label: sample.failureType,
        count: 1,
        severity: sample.severity,
      });
    }
  }
  return [...grouped.values()];
}

function mapReport(raw: RawEvaluationReport, task: EvaluationTask, samples: SampleSummary[]): EvaluationReport {
  const failed = raw.outcome === 'failed' || raw.outcome === 'partial_failed';
  return {
    id: raw.id,
    task,
    verdict: failed ? 'failed' : 'passed',
    verdictReason: failed
      ? '本次评测存在失败或部分失败样本，请结合样本诊断复核。'
      : '本次确定性评测执行完成，未发现执行失败。',
    metrics: raw.metrics.map(mapMetric),
    failures: failureBuckets(samples.filter((sample) => sample.failureType !== 'unclassified')),
    samples,
    generatedAt: raw.generated_at,
    baselineLabel: `${task.modelVersion} · ${task.promptVersion}`,
  };
}

function diagnosisRule(raw: Record<string, unknown> | undefined, fallback: string) {
  return {
    label: recordString(raw, 'label', 'category', 'rule', 'code') ?? fallback,
    confidence: recordNumber(raw, 'confidence', 'score'),
    severity: normalizeSeverity(recordString(raw, 'severity')),
    explanation: recordString(raw, 'explanation', 'message', 'reason') ?? '后端未返回更多诊断说明。',
    evidenceIds: Array.isArray(raw?.evidence_ids)
      ? raw.evidence_ids.filter((value): value is string => typeof value === 'string')
      : [],
  };
}

function mapDiagnosis(raw: RawEvaluationSample, taskId: string): SampleDiagnosis {
  const retrievedDocuments = raw.retrieval_results.map((item, index) => ({
    id: recordString(item, 'doc_id', 'document_id', 'id') ?? `document-${index + 1}`,
    rank: recordNumber(item, 'rank') ?? index + 1,
    title: recordString(item, 'title', 'doc_id', 'document_id') ?? `检索文档 ${index + 1}`,
    source: recordString(item, 'source', 'uri') ?? 'API result',
    score: recordNumber(item, 'score') ?? 0,
    isExpected: item.is_expected === true,
    snippet: recordString(item, 'text', 'snippet', 'content') ?? '',
    chunkId: recordString(item, 'chunk_id') ?? `chunk-${index + 1}`,
  }));
  return {
    id: raw.id,
    taskId,
    question: raw.question,
    expectedAnswer: '',
    generatedAnswer: raw.answer ?? '',
    metrics: raw.metric_results.map(mapMetric),
    primaryDiagnosis: diagnosisRule(raw.diagnoses[0], 'unclassified'),
    secondaryDiagnoses: raw.diagnoses.slice(1).map((item) => diagnosisRule(item, 'unclassified')),
    retrievedDocuments,
    citations: [],
    traceId: raw.id,
    evaluatedAt: raw.reviewed_at ?? now(),
    warnings: raw.diagnoses.length === 0 ? ['后端尚未返回样本级诊断规则。'] : undefined,
  };
}

class MockApiClient implements ApiClient {
  private readonly datasetsState = clone(datasets);
  private readonly tasksState = clone(evaluationTasks);
  private readonly reportState = clone(report);

  constructor(private readonly delayMs: number) {}

  private async respond<T>(value: T): Promise<T> {
    if (this.delayMs > 0) {
      await new Promise((resolve) => window.setTimeout(resolve, this.delayMs));
    }
    return clone(value);
  }

  getProjectOverview(_projectId: string): Promise<ProjectOverview> {
    return this.respond({ ...projectOverview, recentTasks: this.tasksState.slice(0, 3) });
  }

  listDatasets(_projectId: string): Promise<Dataset[]> {
    return this.respond(this.datasetsState);
  }

  async createDataset(_projectId: string, input: DatasetCreateInput): Promise<Dataset> {
    const created: Dataset = {
      id: `mock-dataset-${Date.now()}`,
      name: input.name,
      description: input.description ?? '',
      sampleCount: input.samples?.length ?? 0,
      status: 'draft',
      version: input.version ?? 'v1',
      coverage: 0,
      updatedAt: now(),
      owner: input.owner,
    };
    this.datasetsState.unshift(created);
    return this.respond(created);
  }

  listEvaluationTasks(_projectId: string): Promise<EvaluationTask[]> {
    return this.respond(this.tasksState);
  }

  async createEvaluationTask(_projectId: string, input: EvaluationTaskCreateInput): Promise<EvaluationTask> {
    const dataset = this.datasetsState.find((candidate) => candidate.id === input.datasetId);
    const created: EvaluationTask = {
      id: `mock-evaluation-${Date.now()}`,
      name: input.name ?? `Mock evaluation · ${input.modelVersion}`,
      datasetId: input.datasetId,
      datasetName: dataset?.name ?? input.datasetId,
      status: 'queued',
      progress: 0,
      createdAt: now(),
      modelVersion: input.modelVersion,
      promptVersion: input.promptVersion,
      totalSamples: dataset?.sampleCount ?? 0,
    };
    this.tasksState.unshift(created);
    return this.respond(created);
  }

  getEvaluationReport(_projectId: string, taskId: string): Promise<EvaluationReport> {
    if (taskId !== this.reportState.task.id) {
      return Promise.reject(new ApiError('找不到指定评测报告', 404, 'REPORT_NOT_FOUND'));
    }
    return this.respond(this.reportState);
  }

  async exportEvaluationReport(projectId: string, taskId: string): Promise<ReportExport> {
    return {
      schemaVersion: '1.0',
      exportedAt: now(),
      report: await this.getEvaluationReport(projectId, taskId),
    };
  }

  getSampleDiagnosis(_projectId: string, taskId: string, sampleId: string): Promise<SampleDiagnosis> {
    if (taskId !== diagnosis.taskId || sampleId !== diagnosis.id) {
      return Promise.reject(new ApiError('找不到指定样本诊断', 404, 'DIAGNOSIS_NOT_FOUND'));
    }
    return this.respond(diagnosis);
  }

  async updateSampleReview(
    _projectId: string,
    taskId: string,
    sampleId: string,
    reviewStatus: SampleReviewStatus,
  ): Promise<SampleSummary> {
    if (taskId !== this.reportState.task.id) {
      throw new ApiError('找不到指定评测任务', 404, 'EVALUATION_NOT_FOUND');
    }
    const sample = this.reportState.samples.find((candidate) => candidate.id === sampleId);
    if (!sample) throw new ApiError('找不到指定评测样本', 404, 'SAMPLE_NOT_FOUND');
    sample.reviewStatus = reviewStatus;
    return this.respond(sample);
  }
}

class HttpApiClient implements ApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string, private readonly fetcher: typeof fetch) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  private async request<T>(
    path: string,
    options: { method?: 'GET' | 'POST' | 'PATCH'; body?: unknown; headers?: Record<string, string> } = {},
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10_000);
    const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';

    try {
      const response = await this.fetcher(`${this.baseUrl}${path}`, {
        method: options.method ?? 'GET',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });
      const payload = (await response.json().catch(() => null)) as T | { data: T } | StructuredErrorPayload | null;

      if (!response.ok) {
        const errorPayload = payload as StructuredErrorPayload | null;
        const detail = Array.isArray(errorPayload?.detail)
          ? JSON.stringify(errorPayload.detail)
          : errorPayload?.detail;
        throw new ApiError(
          errorPayload?.error?.message
            ?? detail
            ?? errorPayload?.message
            ?? `请求失败（HTTP ${response.status}）`,
          response.status,
          errorPayload?.error?.code ?? errorPayload?.code,
        );
      }
      if (payload === null) {
        throw new ApiError('后端返回了空响应', response.status, 'EMPTY_RESPONSE');
      }
      if (typeof payload === 'object' && 'data' in payload) return payload.data;
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

  async getProjectOverview(projectId: string): Promise<ProjectOverview> {
    const [datasetsResult, recentTasks] = await Promise.all([
      this.listDatasets(projectId),
      this.listEvaluationTasks(projectId),
    ]);
    return {
      project: {
        id: projectId,
        name: projectId === 'demo' ? 'RAGOps API Workspace' : projectId,
        description: '由后端 MVP 资源接口聚合的项目概览。',
        environment: 'api',
        updatedAt: recentTasks[0]?.createdAt ?? datasetsResult[0]?.updatedAt ?? now(),
      },
      metrics: [],
      recentTasks: recentTasks.slice(0, 5),
      failureDistribution: [],
      trend: [],
      warnings: ['后端 MVP 尚未提供项目聚合指标与趋势接口；当前仅聚合数据集和评测任务。'],
    };
  }

  async listDatasets(_projectId: string): Promise<Dataset[]> {
    const payload = await this.request<RawDatasetList>('/datasets');
    return payload.items.map(mapDataset);
  }

  async createDataset(_projectId: string, input: DatasetCreateInput): Promise<Dataset> {
    const payload = await this.request<RawDataset>('/datasets', {
      method: 'POST',
      body: {
        name: input.name,
        description: input.description || null,
        owner: input.owner,
        version: input.version ?? 'v1',
        schema_version: '1.0',
        samples: (input.samples ?? []).map((sample) => ({
          schema_version: '1.0',
          sample_id: sample.sampleId,
          question: sample.question,
          reference_answer: sample.referenceAnswer ?? null,
          tags: sample.tags ?? [],
        })),
      },
    });
    return mapDataset(payload);
  }

  async listEvaluationTasks(_projectId: string): Promise<EvaluationTask[]> {
    const payload = await this.request<RawEvaluationJobList>('/evaluation-jobs');
    return payload.items.map((job) => mapTask(job));
  }

  async createEvaluationTask(_projectId: string, input: EvaluationTaskCreateInput): Promise<EvaluationTask> {
    const payload = await this.request<RawEvaluationJob>('/evaluation-jobs', {
      method: 'POST',
      body: {
        dataset_id: input.datasetId,
        name: input.name ?? null,
        model_version: input.modelVersion,
        prompt_version: input.promptVersion,
      },
    });
    return mapTask(payload);
  }

  async getEvaluationReport(_projectId: string, taskId: string): Promise<EvaluationReport> {
    const [job, rawReport, sampleList] = await Promise.all([
      this.request<RawEvaluationJob>(`/evaluation-jobs/${taskId}`),
      this.request<RawEvaluationReport>(`/evaluation-jobs/${taskId}/report`),
      this.request<RawEvaluationSampleList>(`/evaluation-jobs/${taskId}/samples`),
    ]);
    return mapReport(rawReport, mapTask(job), sampleList.items.map(mapSample));
  }

  async exportEvaluationReport(_projectId: string, taskId: string): Promise<ReportExport> {
    const [raw, job] = await Promise.all([
      this.request<RawReportExport>(`/evaluation-jobs/${taskId}/report/export`),
      this.request<RawEvaluationJob>(`/evaluation-jobs/${taskId}`),
    ]);
    return {
      schemaVersion: raw.schema_version,
      exportedAt: raw.exported_at,
      report: mapReport(raw.report, mapTask(job), raw.samples.map(mapSample)),
    };
  }

  async getSampleDiagnosis(_projectId: string, taskId: string, sampleId: string): Promise<SampleDiagnosis> {
    const payload = await this.request<RawEvaluationSampleList>(`/evaluation-jobs/${taskId}/samples`);
    const sample = payload.items.find((candidate) => candidate.id === sampleId || candidate.sample_id === sampleId);
    if (!sample) throw new ApiError('找不到指定样本诊断', 404, 'SAMPLE_NOT_FOUND');
    return mapDiagnosis(sample, taskId);
  }

  async updateSampleReview(
    _projectId: string,
    taskId: string,
    sampleId: string,
    reviewStatus: SampleReviewStatus,
  ): Promise<SampleSummary> {
    const payload = await this.request<RawEvaluationSample>(
      `/evaluation-jobs/${taskId}/samples/${sampleId}/review`,
      { method: 'PATCH', body: { review_status: reviewStatus } },
    );
    return mapSample(payload);
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
