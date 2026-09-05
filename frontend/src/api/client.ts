import { datasets, diagnosis, evaluationTasks, projectOverview, report } from './fixtures';
import type {
  ApiClient,
  CitationEvidence,
  ContextEvidence,
  Dataset,
  DatasetCreateInput,
  DatasetImportResult,
  DatasetSampleInput,
  EvaluationReport,
  EvaluationTask,
  EvaluationTaskCreateInput,
  ExecutionSnapshot,
  FailureBucket,
  MetricStatus,
  MetricValue,
  ModelErrorSummary,
  ModelExecutionStatus,
  ProjectOverview,
  ProviderConfigurationStatus,
  QualityStatus,
  QualityVerdict,
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
  schema_version?: string;
  status: 'draft' | 'published';
  sample_count: number;
  content_sha256?: string | null;
  created_at: string;
  published_at: string | null;
}

interface RawDatasetList {
  items: RawDataset[];
  total: number;
  next_cursor: string | null;
}

interface RawDatasetImportResult {
  accepted: number;
  rejected: number;
  dataset: RawDataset;
}

interface RawEvaluationJob {
  id: string;
  dataset_id: string;
  name: string;
  schema_version?: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  outcome: 'succeeded' | 'partial_failed' | 'failed' | null;
  config_version?: string;
  model_version?: string;
  prompt_version?: string;
  metric_config?: Array<Record<string, unknown>>;
  total_count: number;
  queued_count?: number;
  running_count?: number;
  succeeded_count: number;
  failed_count: number;
  progress: number;
  failure_code?: string | null;
  failure_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at: string | null;
  adapter_id?: string;
  provider_id?: string | null;
  execution_snapshot?: Record<string, unknown> | null;
  quality_status?: string;
  quality_verdict?: string;
  quality_score?: number | null;
}

interface RawEvaluationJobList {
  items: RawEvaluationJob[];
  total: number;
}

interface RawEvaluationSample {
  id: string;
  sample_id: string;
  schema_version?: string;
  question: string;
  status?: string;
  answer?: string | null;
  reference_answer?: string | null;
  historical_answer?: string | null;
  labels?: Record<string, unknown>;
  run?: Record<string, unknown> | null;
  retrieval_results?: Array<Record<string, unknown>>;
  citations?: Array<Record<string, unknown>>;
  metric_results?: Array<Record<string, unknown>>;
  diagnoses?: Array<Record<string, unknown>>;
  quality_status?: string;
  review_status: SampleReviewStatus;
  reviewed_at: string | null;
  latency_ms?: number | null;
  failure_code?: string | null;
  failure_message?: string | null;
}

interface RawEvaluationSampleList {
  items: RawEvaluationSample[];
  total: number;
}

interface RawEvaluationReport {
  id: string;
  job_id: string;
  schema_version?: string;
  status: RawEvaluationJob['status'];
  outcome?: Exclude<RawEvaluationJob['outcome'], null>;
  generated_at?: string | null;
  summary?: Record<string, number>;
  execution_summary?: Record<string, unknown>;
  quality_summary?: Record<string, unknown>;
  execution_snapshot?: Record<string, unknown> | null;
  metrics?: Array<Record<string, unknown>>;
}

interface RawReportExport {
  schema_version: string;
  exported_at: string;
  report: RawEvaluationReport;
  samples: RawEvaluationSample[];
}

interface RawModelExecutionStatus {
  schema_version?: string;
  backend_execution_adapter?: string;
  external_calls_enabled?: boolean;
  execution_available?: boolean;
  active_adapter?: Record<string, unknown> | null;
  providers?: Array<Record<string, unknown>>;
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

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

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

function recordBoolean(record: Record<string, unknown> | undefined, ...keys: string[]): boolean | null {
  for (const key of keys) {
    const value = record?.[key];
    if (typeof value === 'boolean') return value;
  }
  return null;
}

function recordStringArray(record: Record<string, unknown> | undefined, key: string): string[] {
  const value = record?.[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function recordArray(record: Record<string, unknown> | undefined, key: string): Array<Record<string, unknown>> {
  const value = record?.[key];
  return Array.isArray(value) ? value.map(asRecord).filter((item): item is Record<string, unknown> => Boolean(item)) : [];
}

function qualityStatus(value: unknown, fallback: QualityStatus = 'legacy_unknown'): QualityStatus {
  return value === 'not_evaluated' || value === 'evaluated' || value === 'partial' || value === 'error' || value === 'legacy_unknown'
    ? value
    : fallback;
}

function qualityVerdict(value: unknown): QualityVerdict {
  return value === 'passed' || value === 'failed' ? value : 'unknown';
}

function metricStatus(value: unknown): MetricStatus {
  return value === 'ok' || value === 'not_evaluated' || value === 'not_applicable' || value === 'unknown' || value === 'error' || value === 'legacy'
    ? value
    : 'legacy';
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
    schemaVersion: raw.schema_version ?? '1.0',
    version: raw.version,
    contentSha256: raw.content_sha256 ?? null,
    coverage: null,
    updatedAt: raw.published_at ?? raw.created_at,
    owner: raw.owner,
  };
}

function mapExecutionSnapshot(raw: Record<string, unknown> | null | undefined): ExecutionSnapshot | null {
  if (!raw) return null;
  const prompt = asRecord(raw.prompt);
  const generation = asRecord(raw.generation);
  const dataset = asRecord(raw.dataset);
  const adapterId = recordString(raw, 'adapter_id');
  const promptVersion = recordString(prompt, 'version');
  const promptText = recordString(prompt, 'text');
  const model = recordString(generation, 'model');
  const temperature = recordNumber(generation, 'temperature');
  const topP = recordNumber(generation, 'top_p');
  const maxOutputTokens = recordNumber(generation, 'max_output_tokens');
  const datasetId = recordString(dataset, 'id');
  const datasetVersion = recordString(dataset, 'version');
  const datasetSchemaVersion = recordString(dataset, 'schema_version');
  const contextPolicy = recordString(raw, 'context_policy');
  const externalCallsEnabledAtCreation = recordBoolean(raw, 'external_calls_enabled_at_creation');
  const createdAt = recordString(raw, 'created_at');
  const configVersion = recordString(raw, 'config_version');
  if (!adapterId || !promptVersion || !promptText || !model || temperature === null || topP === null || maxOutputTokens === null
    || !datasetId || !datasetVersion || !datasetSchemaVersion || externalCallsEnabledAtCreation === null || !createdAt || !configVersion
    || !Array.isArray(generation?.stop) || !Array.isArray(raw.metric_config)) return null;
  if (contextPolicy !== 'dataset_contexts' && contextPolicy !== 'none' && contextPolicy !== 'retrieval') return null;
  return {
    contractVersion: recordString(raw, 'contract_version') ?? '2.0',
    adapterId,
    providerId: recordString(raw, 'provider_id') ?? null,
    prompt: { version: promptVersion, text: promptText },
    generation: {
      model,
      temperature,
      topP,
      maxOutputTokens,
      stop: recordStringArray(generation, 'stop'),
      seed: recordNumber(generation, 'seed'),
    },
    contextPolicy,
    dataset: {
      id: datasetId,
      version: datasetVersion,
      schemaVersion: datasetSchemaVersion,
      contentSha256: recordString(dataset, 'content_sha256') ?? null,
    },
    metricConfig: recordArray(raw, 'metric_config'),
    qualityGate: asRecord(raw.quality_gate) ?? null,
    externalCallsEnabledAtCreation,
    createdAt,
    configVersion,
  };
}

function mapTask(raw: RawEvaluationJob, datasetName = raw.dataset_id): EvaluationTask {
  const snapshot = mapExecutionSnapshot(raw.execution_snapshot);
  const schemaVersion = raw.schema_version ?? '1.0';
  const adapterId = snapshot?.adapterId ?? raw.adapter_id ?? null;
  const isMock = adapterId === 'mock' ? true : null;
  return {
    id: raw.id,
    name: raw.name,
    datasetId: raw.dataset_id,
    datasetName,
    status: raw.status,
    outcome: raw.outcome,
    qualityStatus: qualityStatus(raw.quality_status),
    qualityVerdict: qualityVerdict(raw.quality_verdict),
    qualityScore: typeof raw.quality_score === 'number' && Number.isFinite(raw.quality_score) ? raw.quality_score : null,
    progress: Math.round(raw.progress * 100),
    createdAt: raw.created_at,
    completedAt: raw.finished_at,
    modelVersion: snapshot?.generation.model ?? (schemaVersion === '2.0' ? raw.model_version ?? null : null),
    promptVersion: snapshot?.prompt.version ?? raw.prompt_version ?? null,
    adapterId,
    providerId: snapshot?.providerId ?? raw.provider_id ?? null,
    isMock,
    totalSamples: raw.total_count,
    succeededSamples: raw.succeeded_count,
    failedSamples: raw.failed_count,
    schemaVersion,
    executionSnapshot: snapshot,
    failureCode: raw.failure_code ?? null,
    failureMessage: raw.failure_message ?? null,
  };
}

function mapMetric(record: Record<string, unknown>, index: number): MetricValue {
  const key = recordString(record, 'metric_name', 'name', 'key') ?? `metric-${index + 1}`;
  const status = metricStatus(record.status);
  const rawValue = record.value ?? record.score;
  const value = typeof rawValue === 'number' && Number.isFinite(rawValue)
    ? rawValue
    : typeof rawValue === 'boolean' ? rawValue : null;
  return {
    key,
    label: key.replaceAll('_', ' '),
    value,
    status,
    evaluatedCount: recordNumber(record, 'evaluated_count'),
    excludedCount: recordNumber(record, 'excluded_count'),
    details: asRecord(record.details),
  };
}

function findMetric(metrics: MetricValue[], ...names: string[]): MetricValue | undefined {
  return metrics.find((metric) => names.includes(metric.key));
}

function mapModelError(raw: Record<string, unknown> | null | undefined): ModelErrorSummary | null {
  if (!raw) return null;
  const code = recordString(raw, 'code');
  if (!code) return null;
  return {
    code,
    message: recordString(raw, 'message') ?? '执行失败，后端未返回安全说明。',
    retryable: recordBoolean(raw, 'retryable') ?? false,
    attempts: recordNumber(raw, 'attempts') ?? 0,
    providerRequestId: recordString(raw, 'provider_request_id') ?? null,
    retryAfterMs: recordNumber(raw, 'retry_after_ms'),
  };
}

function mapContexts(
  records: Array<Record<string, unknown>>,
  goldDocumentIds: string[],
  legacy = false,
): ContextEvidence[] {
  return records.map((item, index) => {
    const originValue = recordString(item, 'origin');
    const origin = originValue === 'provided' || originValue === 'retrieved' || originValue === 'legacy_unknown'
      ? originValue
      : legacy ? 'legacy_unknown' : 'legacy_unknown';
    const docId = recordString(item, 'doc_id', 'document_id') ?? null;
    const chunkId = recordString(item, 'chunk_id') ?? null;
    const rank = recordNumber(item, 'rank');
    return {
      key: `${origin}:${rank ?? 'unknown'}:${docId ?? chunkId ?? index}`,
      origin,
      rank,
      rankBefore: recordNumber(item, 'rank_before'),
      retrievalRunId: recordString(item, 'retrieval_run_id') ?? null,
      docId,
      chunkId,
      evidenceIds: recordStringArray(item, 'evidence_ids'),
      text: recordString(item, 'text', 'snippet', 'content') ?? '',
      score: recordNumber(item, 'score'),
      relevanceGrade: recordNumber(item, 'relevance_grade'),
      usefulness: recordBoolean(item, 'usefulness'),
      title: recordString(item, 'title') ?? null,
      source: recordString(item, 'source', 'uri') ?? null,
      isExpected: docId !== null && goldDocumentIds.includes(docId),
    };
  });
}

function mapCitations(records: Array<Record<string, unknown>>): CitationEvidence[] {
  return records.map((item, index) => {
    const targetType = recordString(item, 'target_type');
    const normalizedTargetType: CitationEvidence['targetType'] = targetType === 'context_item' || targetType === 'document' || targetType === 'external'
      ? targetType
      : null;
    const raw = recordString(item, 'raw') ?? '';
    return {
      id: recordString(item, 'citation_id', 'id') ?? `citation-${index + 1}`,
      marker: raw || recordString(item, 'citation_id') || `引用 ${index + 1}`,
      claimId: recordString(item, 'claim_id') ?? null,
      raw,
      targetType: normalizedTargetType,
      targetId: recordString(item, 'target_id') ?? null,
      resolved: recordBoolean(item, 'resolved'),
      supportsClaim: recordBoolean(item, 'supports_claim'),
      supportJudgeVersion: recordString(item, 'support_judge_version') ?? null,
    };
  });
}

function sampleParts(raw: RawEvaluationSample) {
  const labels = asRecord(raw.labels);
  const run = asRecord(raw.run);
  const goldDocumentIds = recordStringArray(labels, 'gold_document_ids');
  const runContexts = recordArray(run, 'contexts');
  const contexts = runContexts.length > 0
    ? mapContexts(runContexts, goldDocumentIds)
    : mapContexts(raw.retrieval_results ?? [], goldDocumentIds, true);
  const citations = mapCitations(recordArray(run, 'citations').length > 0 ? recordArray(run, 'citations') : raw.citations ?? []);
  const metrics = (raw.metric_results ?? []).map(mapMetric);
  const runStatusValue = recordString(run, 'status') ?? raw.status;
  const runStatus: SampleSummary['runStatus'] = runStatusValue === 'queued' || runStatusValue === 'running' || runStatusValue === 'succeeded' || runStatusValue === 'failed' || runStatusValue === 'cancelled'
    ? runStatusValue
    : 'legacy_unknown';
  const error = mapModelError(asRecord(run?.error)) ?? (raw.failure_code ? {
    code: raw.failure_code,
    message: raw.failure_message ?? '旧运行失败，未记录更多安全说明。',
    retryable: false,
    attempts: 0,
    providerRequestId: null,
    retryAfterMs: null,
  } : null);
  return {
    labels,
    run,
    contexts,
    citations,
    metrics,
    runStatus,
    error,
    referenceAnswer: recordString(labels, 'reference_answer') ?? raw.reference_answer ?? null,
    historicalAnswer: raw.historical_answer ?? null,
    generatedAnswer: run && typeof run.answer === 'string' ? run.answer : raw.answer ?? null,
  };
}

function mapSample(raw: RawEvaluationSample): SampleSummary {
  const parts = sampleParts(raw);
  const diagnoses = raw.diagnoses ?? [];
  const diagnosisRecord = diagnoses[0];
  const recall = findMetric(parts.metrics, 'recall_at_5');
  const faithfulness = findMetric(parts.metrics, 'faithfulness');
  const citationSupport = findMetric(parts.metrics, 'citation_support_rate', 'citation_hit_rate');
  return {
    id: raw.id,
    sampleId: raw.sample_id,
    question: raw.question,
    referenceAnswer: parts.referenceAnswer,
    historicalAnswer: parts.historicalAnswer,
    generatedAnswer: parts.generatedAnswer,
    failureType: recordString(diagnosisRecord, 'rule_id', 'category', 'label', 'rule', 'code') ?? 'unclassified',
    severity: normalizeSeverity(recordString(diagnosisRecord, 'severity')),
    recallAt5: typeof recall?.value === 'number' ? recall.value : null,
    recallAt5Status: recall?.status ?? 'not_evaluated',
    faithfulness: typeof faithfulness?.value === 'number' ? faithfulness.value : null,
    faithfulnessStatus: faithfulness?.status ?? 'not_evaluated',
    citationSupportRate: typeof citationSupport?.value === 'number' ? citationSupport.value : null,
    citationSupportStatus: citationSupport?.status ?? 'not_evaluated',
    latencyMs: recordNumber(parts.run, 'latency_ms') ?? (typeof raw.latency_ms === 'number' ? raw.latency_ms : null),
    runStatus: parts.runStatus,
    qualityStatus: qualityStatus(raw.quality_status),
    reviewStatus: raw.review_status,
    contexts: parts.contexts,
    citations: parts.citations,
    error: parts.error,
    isMock: recordBoolean(parts.run, 'is_mock'),
  };
}

function failureBuckets(samples: SampleSummary[]): FailureBucket[] {
  const grouped = new Map<string, FailureBucket>();
  for (const sample of samples) {
    if (sample.failureType === 'unclassified') continue;
    const current = grouped.get(sample.failureType);
    if (current) current.count += 1;
    else grouped.set(sample.failureType, {
      key: sample.failureType,
      label: sample.failureType,
      count: 1,
      severity: sample.severity,
    });
  }
  return [...grouped.values()];
}

function mapReport(raw: RawEvaluationReport, task: EvaluationTask, samples: SampleSummary[]): EvaluationReport {
  const executionRaw = raw.execution_summary;
  const qualityRaw = raw.quality_summary;
  const outcomeValue = recordString(executionRaw, 'outcome') ?? raw.outcome ?? task.outcome;
  const outcome = outcomeValue === 'succeeded' || outcomeValue === 'partial_failed' || outcomeValue === 'failed' ? outcomeValue : null;
  const totalCount = recordNumber(executionRaw, 'total_count') ?? raw.summary?.total_count ?? task.totalSamples;
  const succeededCount = recordNumber(executionRaw, 'succeeded_count') ?? raw.summary?.succeeded_count ?? task.succeededSamples;
  const failedCount = recordNumber(executionRaw, 'failed_count') ?? raw.summary?.failed_count ?? task.failedSamples;
  const explicitSuccessRate = recordNumber(executionRaw, 'success_rate');
  const successRate = explicitSuccessRate ?? (totalCount > 0 ? succeededCount / totalCount : null);
  const qualitySummaryStatus = qualityStatus(qualityRaw?.status ?? task.qualityStatus);
  const verdict = qualityVerdict(qualityRaw?.verdict ?? task.qualityVerdict);
  const score = recordNumber(qualityRaw, 'score') ?? task.qualityScore;
  const snapshot = mapExecutionSnapshot(raw.execution_snapshot) ?? task.executionSnapshot;
  const sampleMockStates = samples.map((sample) => sample.isMock).filter((value): value is boolean => value !== null);
  const isSimulated = snapshot?.adapterId === 'mock' || task.isMock === true
    ? true
    : sampleMockStates.some(Boolean) ? true
      : sampleMockStates.length > 0 && sampleMockStates.every((value) => !value) ? false : null;
  const verdictReason = verdict === 'passed'
    ? '已按报告中明确的质量门规则完成评估，结论为通过。'
    : verdict === 'failed'
      ? '已按报告中明确的质量门规则完成评估，结论为不通过。'
      : qualitySummaryStatus === 'not_evaluated'
        ? '任务执行结果已记录；本次没有完成质量门评估，不能据执行成功推断答案质量。'
        : qualitySummaryStatus === 'legacy_unknown'
          ? '旧报告未记录可验证的质量状态，门禁结论保持未知。'
          : qualitySummaryStatus === 'error'
            ? '质量评估发生错误；执行结果与错误记录仍可单独查看。'
            : '部分质量指标不可用，当前无法给出门禁结论。';
  return {
    id: raw.id,
    schemaVersion: raw.schema_version ?? '1.0',
    task,
    verdict: verdict === 'passed' ? 'passed' : verdict === 'failed' ? 'failed' : 'undetermined',
    verdictReason,
    executionSummary: { outcome, totalCount, succeededCount, failedCount, successRate },
    qualitySummary: {
      status: qualitySummaryStatus,
      verdict,
      score,
      evaluatedSampleCount: recordNumber(qualityRaw, 'evaluated_sample_count'),
    },
    executionSnapshot: snapshot,
    isSimulated,
    metrics: (raw.metrics ?? []).map(mapMetric),
    failures: failureBuckets(samples),
    samples,
    generatedAt: raw.generated_at ?? null,
    baselineLabel: null,
    warnings: raw.schema_version === '2.0' ? undefined : ['该报告来自 1.x 兼容记录；模型身份、模拟状态和质量结论不能反推。'],
  };
}

function diagnosisRule(raw: Record<string, unknown> | undefined, fallback: string) {
  return {
    label: recordString(raw, 'rule_id', 'label', 'category', 'rule', 'code') ?? fallback,
    confidence: recordNumber(raw, 'confidence', 'score'),
    severity: normalizeSeverity(recordString(raw, 'severity')),
    explanation: recordString(raw, 'explanation', 'message', 'reason') ?? '后端未返回更多诊断说明。',
    evidenceIds: recordStringArray(raw, 'evidence_ids'),
  };
}

function mapDiagnosis(raw: RawEvaluationSample, taskId: string): SampleDiagnosis {
  const parts = sampleParts(raw);
  const diagnoses = raw.diagnoses ?? [];
  const usage = asRecord(parts.run?.usage);
  const mappedUsage = usage
    && recordNumber(usage, 'input_tokens') !== null
    && recordNumber(usage, 'output_tokens') !== null
    && recordNumber(usage, 'total_tokens') !== null
    ? {
      inputTokens: recordNumber(usage, 'input_tokens') as number,
      outputTokens: recordNumber(usage, 'output_tokens') as number,
      totalTokens: recordNumber(usage, 'total_tokens') as number,
    }
    : null;
  const runId = recordString(parts.run, 'run_id') ?? null;
  return {
    id: raw.id,
    sampleId: raw.sample_id,
    taskId,
    question: raw.question,
    expectedAnswer: parts.referenceAnswer,
    historicalAnswer: parts.historicalAnswer,
    generatedAnswer: parts.generatedAnswer,
    metrics: parts.metrics,
    qualityStatus: qualityStatus(raw.quality_status),
    primaryDiagnosis: diagnosisRule(diagnoses[0], diagnoses.length === 0 ? '未生成诊断' : 'unclassified'),
    secondaryDiagnoses: diagnoses.slice(1).map((item) => diagnosisRule(item, 'unclassified')),
    contexts: parts.contexts,
    citations: parts.citations,
    run: {
      runId,
      status: parts.runStatus,
      adapterId: recordString(parts.run, 'adapter_id') ?? null,
      providerId: recordString(parts.run, 'provider_id') ?? null,
      requestedModel: recordString(parts.run, 'requested_model') ?? null,
      actualModel: recordString(parts.run, 'actual_model') ?? null,
      isMock: recordBoolean(parts.run, 'is_mock'),
      finishReason: recordString(parts.run, 'finish_reason') ?? null,
      latencyMs: recordNumber(parts.run, 'latency_ms') ?? (typeof raw.latency_ms === 'number' ? raw.latency_ms : null),
      usage: mappedUsage,
      cost: recordNumber(parts.run, 'cost'),
      providerRequestId: recordString(parts.run, 'provider_request_id') ?? null,
      attemptCount: recordNumber(parts.run, 'attempt_count'),
      error: parts.error,
      startedAt: recordString(parts.run, 'started_at') ?? null,
      finishedAt: recordString(parts.run, 'finished_at') ?? null,
    },
    reviewStatus: raw.review_status,
    traceId: runId,
    evaluatedAt: recordString(parts.run, 'finished_at') ?? raw.reviewed_at ?? null,
    warnings: diagnoses.length === 0 ? ['后端尚未返回样本级诊断规则。'] : undefined,
  };
}

function serializeSampleInput(sample: DatasetSampleInput) {
  return {
    schema_version: '2.0',
    sample_id: sample.sampleId,
    question: sample.question,
    labels: {
      reference_answer: sample.labels?.referenceAnswer ?? null,
      gold_document_ids: sample.labels?.goldDocumentIds ?? [],
      gold_evidence_ids: sample.labels?.goldEvidenceIds ?? [],
      expected_diagnoses: sample.labels?.expectedDiagnoses ?? [],
    },
    contexts: (sample.contexts ?? []).map((context) => ({
      origin: context.origin,
      rank: context.rank,
      rank_before: context.rankBefore ?? null,
      retrieval_run_id: context.retrievalRunId ?? null,
      doc_id: context.docId,
      chunk_id: context.chunkId,
      evidence_ids: context.evidenceIds ?? [],
      text: context.text,
      score: context.score ?? null,
      relevance_grade: context.relevanceGrade ?? null,
      usefulness: context.usefulness ?? null,
    })),
    historical_output: sample.historicalOutput ? {
      answer: sample.historicalOutput.answer,
      citations: sample.historicalOutput.citations,
      recorded_at: sample.historicalOutput.recordedAt,
    } : null,
    tags: sample.tags ?? [],
    metadata: sample.metadata ?? {},
  };
}

function mapModelExecutionStatus(raw: RawModelExecutionStatus): ModelExecutionStatus {
  const active = raw.active_adapter ?? null;
  const capabilities = asRecord(active?.capabilities);
  const activeAdapterId = recordString(active ?? undefined, 'adapter_id');
  const activeIsMock = recordBoolean(active ?? undefined, 'is_mock');
  const externalNetwork = recordBoolean(capabilities, 'external_network');
  const supportsSeed = recordBoolean(capabilities, 'supports_seed');
  const supportsStop = recordBoolean(capabilities, 'supports_stop');
  const reportsUsage = recordBoolean(capabilities, 'reports_usage');
  const reportsRequestId = recordBoolean(capabilities, 'reports_request_id');
  const activeComplete = activeAdapterId !== undefined && activeIsMock !== null && externalNetwork !== null
    && supportsSeed !== null && supportsStop !== null && reportsUsage !== null && reportsRequestId !== null;
  return {
    schemaVersion: raw.schema_version ?? '2.0',
    backendExecutionAdapter: raw.backend_execution_adapter ?? null,
    externalCallsEnabled: typeof raw.external_calls_enabled === 'boolean' ? raw.external_calls_enabled : null,
    executionAvailable: typeof raw.execution_available === 'boolean' ? raw.execution_available : null,
    activeAdapter: activeComplete ? {
      adapterId: activeAdapterId,
      isMock: activeIsMock,
      capabilities: {
        externalNetwork,
        supportsSeed,
        supportsStop,
        reportsUsage,
        reportsRequestId,
      },
    } : null,
    providers: (raw.providers ?? []).map((item) => {
      const statusValue = recordString(item, 'configuration_status');
      const configurationStatus: ProviderConfigurationStatus = statusValue === 'configured_unverified' || statusValue === 'verified' || statusValue === 'not_configured'
        ? statusValue
        : 'unknown';
      return {
        providerId: recordString(item, 'provider_id') ?? null,
        configurationStatus,
        baseUrlConfigured: recordBoolean(item, 'base_url_configured'),
        credentialConfigured: recordBoolean(item, 'credential_configured'),
        defaultModelConfigured: recordBoolean(item, 'default_model_configured'),
        lastVerifiedAt: recordString(item, 'last_verified_at') ?? null,
        verificationMessage: recordString(item, 'verification_message') ?? null,
      };
    }),
    source: 'api',
  };
}

class MockApiClient implements ApiClient {
  private readonly datasetsState = clone(datasets);
  private readonly tasksState = clone(evaluationTasks);
  private readonly reportState = clone(report);
  private readonly diagnosisState = clone(diagnosis);

  constructor(private readonly delayMs: number) {}

  private async respond<T>(value: T): Promise<T> {
    if (this.delayMs > 0) await new Promise((resolve) => window.setTimeout(resolve, this.delayMs));
    return clone(value);
  }

  getProjectOverview(_projectId: string): Promise<ProjectOverview> {
    return this.respond({ ...projectOverview, recentTasks: this.tasksState.slice(0, 3) });
  }

  getModelExecutionStatus(): Promise<ModelExecutionStatus> {
    return this.respond({
      schemaVersion: '2.0',
      backendExecutionAdapter: 'mock',
      externalCallsEnabled: false,
      executionAvailable: true,
      activeAdapter: {
        adapterId: 'mock',
        isMock: true,
        capabilities: {
          externalNetwork: false,
          supportsSeed: true,
          supportsStop: true,
          reportsUsage: false,
          reportsRequestId: false,
        },
      },
      providers: [{
        providerId: 'openai_compatible',
        configurationStatus: 'not_configured',
        baseUrlConfigured: false,
        credentialConfigured: false,
        defaultModelConfigured: false,
        lastVerifiedAt: null,
        verificationMessage: null,
      }],
      source: 'fixture',
    });
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
      schemaVersion: '2.0',
      version: input.version ?? 'v1',
      contentSha256: null,
      coverage: null,
      updatedAt: now(),
      owner: input.owner,
    };
    this.datasetsState.unshift(created);
    return this.respond(created);
  }

  async importDatasetSamples(_projectId: string, datasetId: string, samples: DatasetSampleInput[]): Promise<DatasetImportResult> {
    const dataset = this.datasetsState.find((candidate) => candidate.id === datasetId);
    if (!dataset) throw new ApiError('找不到指定数据集', 404, 'DATASET_NOT_FOUND');
    if (dataset.status !== 'draft') throw new ApiError('已发布数据集不可继续导入样本', 409, 'DATASET_IMMUTABLE');
    dataset.sampleCount += samples.length;
    dataset.updatedAt = now();
    return this.respond({ accepted: samples.length, rejected: 0, dataset });
  }

  async publishDataset(_projectId: string, datasetId: string): Promise<Dataset> {
    const dataset = this.datasetsState.find((candidate) => candidate.id === datasetId);
    if (!dataset) throw new ApiError('找不到指定数据集', 404, 'DATASET_NOT_FOUND');
    if (dataset.sampleCount === 0) throw new ApiError('数据集至少需要一条样本才能发布', 409, 'DATASET_EMPTY');
    dataset.status = 'ready';
    dataset.contentSha256 = `mock-${dataset.id}`;
    dataset.updatedAt = now();
    return this.respond(dataset);
  }

  listEvaluationTasks(_projectId: string): Promise<EvaluationTask[]> {
    return this.respond(this.tasksState);
  }

  async createEvaluationTask(_projectId: string, input: EvaluationTaskCreateInput): Promise<EvaluationTask> {
    if (input.adapterId !== 'mock') {
      throw new ApiError('Mock 工作台未配置真实提供方；未回退到 mock 执行。', 409, 'PROVIDER_NOT_CONFIGURED');
    }
    if (input.contextPolicy === 'retrieval') {
      throw new ApiError('本阶段尚未提供检索执行方式；未改用给定上下文。', 409, 'EXECUTION_MODE_UNAVAILABLE');
    }
    const dataset = this.datasetsState.find((candidate) => candidate.id === input.datasetId);
    if (!dataset) throw new ApiError('找不到指定数据集', 404, 'DATASET_NOT_FOUND');
    if (dataset.status !== 'ready') throw new ApiError('请先发布数据集再创建任务', 409, 'DATASET_NOT_PUBLISHED');
    const createdAt = now();
    const snapshot: ExecutionSnapshot = {
      contractVersion: '2.0',
      adapterId: 'mock',
      providerId: null,
      prompt: input.prompt,
      generation: input.generation,
      contextPolicy: input.contextPolicy,
      dataset: {
        id: dataset.id,
        version: dataset.version,
        schemaVersion: dataset.schemaVersion,
        contentSha256: dataset.contentSha256,
      },
      metricConfig: input.metrics ?? [],
      qualityGate: input.qualityGate ?? null,
      externalCallsEnabledAtCreation: false,
      createdAt,
      configVersion: `mock-config-${Date.now()}`,
    };
    const created: EvaluationTask = {
      id: `mock-evaluation-${Date.now()}`,
      name: input.name ?? `${dataset.name} mock evaluation`,
      datasetId: input.datasetId,
      datasetName: dataset.name,
      status: 'queued',
      outcome: null,
      qualityStatus: 'not_evaluated',
      qualityVerdict: 'unknown',
      qualityScore: null,
      progress: 0,
      createdAt,
      completedAt: null,
      modelVersion: input.generation.model,
      promptVersion: input.prompt.version,
      adapterId: 'mock',
      providerId: null,
      isMock: true,
      totalSamples: dataset.sampleCount,
      succeededSamples: 0,
      failedSamples: 0,
      schemaVersion: '2.0',
      executionSnapshot: snapshot,
    };
    this.tasksState.unshift(created);
    return this.respond(created);
  }

  getEvaluationReport(_projectId: string, taskId: string): Promise<EvaluationReport> {
    if (taskId !== this.reportState.task.id) return Promise.reject(new ApiError('找不到指定评测报告', 404, 'REPORT_NOT_FOUND'));
    return this.respond(this.reportState);
  }

  async exportEvaluationReport(projectId: string, taskId: string): Promise<ReportExport> {
    const exportedAt = now();
    const currentReport = await this.getEvaluationReport(projectId, taskId);
    const samples = currentReport.samples.map((sample) => sample.sampleId === this.diagnosisState.sampleId ? this.diagnosisState : null)
      .filter((sample): sample is SampleDiagnosis => sample !== null);
    const artifact = {
      schema_version: '2.0',
      exported_at: exportedAt,
      simulated: true,
      report: currentReport,
      samples,
    };
    return { schemaVersion: '2.0', exportedAt, report: currentReport, samples, artifact };
  }

  getSampleDiagnosis(_projectId: string, taskId: string, sampleId: string): Promise<SampleDiagnosis> {
    if (taskId !== this.diagnosisState.taskId || (sampleId !== this.diagnosisState.id && sampleId !== this.diagnosisState.sampleId)) {
      return Promise.reject(new ApiError('找不到指定样本诊断', 404, 'DIAGNOSIS_NOT_FOUND'));
    }
    return this.respond(this.diagnosisState);
  }

  async updateSampleReview(
    _projectId: string,
    taskId: string,
    sampleId: string,
    reviewStatus: SampleReviewStatus,
  ): Promise<SampleSummary> {
    if (taskId !== this.reportState.task.id) throw new ApiError('找不到指定评测任务', 404, 'EVALUATION_NOT_FOUND');
    const sample = this.reportState.samples.find((candidate) => candidate.id === sampleId || candidate.sampleId === sampleId);
    if (!sample) throw new ApiError('找不到指定评测样本', 404, 'SAMPLE_NOT_FOUND');
    sample.reviewStatus = reviewStatus;
    if (this.diagnosisState.sampleId === sample.sampleId) this.diagnosisState.reviewStatus = reviewStatus;
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
        const detail = typeof errorPayload?.detail === 'string' ? errorPayload.detail : undefined;
        throw new ApiError(
          errorPayload?.error?.message ?? detail ?? errorPayload?.message ?? `请求失败（HTTP ${response.status}）`,
          response.status,
          errorPayload?.error?.code ?? errorPayload?.code,
        );
      }
      if (payload === null) throw new ApiError('后端返回了空响应', response.status, 'EMPTY_RESPONSE');
      if (typeof payload === 'object' && 'data' in payload) return payload.data;
      return payload as T;
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') throw new ApiError('请求超时，请稍后重试', undefined, 'TIMEOUT');
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async getProjectOverview(projectId: string): Promise<ProjectOverview> {
    const [datasetsResult, recentTasks] = await Promise.all([this.listDatasets(projectId), this.listEvaluationTasks(projectId)]);
    return {
      project: {
        id: projectId,
        name: projectId === 'demo' ? 'RAGOps API Workspace' : projectId,
        description: '由后端资源接口聚合的项目概览。',
        environment: 'api',
        updatedAt: recentTasks[0]?.createdAt ?? datasetsResult[0]?.updatedAt ?? now(),
      },
      metrics: [],
      recentTasks: recentTasks.slice(0, 5),
      failureDistribution: [],
      trend: [],
      warnings: ['后端尚未提供项目聚合指标与趋势接口；当前仅展示可追溯的数据集和任务，不推算质量分。'],
    };
  }

  async getModelExecutionStatus(): Promise<ModelExecutionStatus> {
    return mapModelExecutionStatus(await this.request<RawModelExecutionStatus>('/model-execution/status'));
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
        schema_version: '2.0',
        samples: (input.samples ?? []).map(serializeSampleInput),
      },
    });
    return mapDataset(payload);
  }

  async importDatasetSamples(_projectId: string, datasetId: string, samples: DatasetSampleInput[]): Promise<DatasetImportResult> {
    const payload = await this.request<RawDatasetImportResult>(`/datasets/${datasetId}/samples:import`, {
      method: 'POST',
      body: { samples: samples.map(serializeSampleInput) },
    });
    return { accepted: payload.accepted, rejected: payload.rejected, dataset: mapDataset(payload.dataset) };
  }

  async publishDataset(_projectId: string, datasetId: string): Promise<Dataset> {
    return mapDataset(await this.request<RawDataset>(`/datasets/${datasetId}:publish`, { method: 'POST' }));
  }

  async listEvaluationTasks(_projectId: string): Promise<EvaluationTask[]> {
    const payload = await this.request<RawEvaluationJobList>('/evaluation-jobs');
    return payload.items.map((job) => mapTask(job));
  }

  async createEvaluationTask(_projectId: string, input: EvaluationTaskCreateInput): Promise<EvaluationTask> {
    const payload = await this.request<RawEvaluationJob>('/evaluation-jobs', {
      method: 'POST',
      body: {
        schema_version: '2.0',
        dataset_id: input.datasetId,
        name: input.name ?? null,
        execution: {
          adapter_id: input.adapterId,
          prompt: { version: input.prompt.version, text: input.prompt.text },
          generation: {
            model: input.generation.model,
            temperature: input.generation.temperature,
            top_p: input.generation.topP,
            max_output_tokens: input.generation.maxOutputTokens,
            stop: input.generation.stop,
            seed: input.generation.seed,
          },
          context_policy: input.contextPolicy,
        },
        metrics: input.metrics ?? [],
        quality_gate: input.qualityGate ?? null,
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
    const task = mapTask(job);
    return mapReport(rawReport, task, sampleList.items.map(mapSample));
  }

  async exportEvaluationReport(_projectId: string, taskId: string): Promise<ReportExport> {
    const [raw, job] = await Promise.all([
      this.request<RawReportExport>(`/evaluation-jobs/${taskId}/report/export`),
      this.request<RawEvaluationJob>(`/evaluation-jobs/${taskId}`),
    ]);
    const task = mapTask(job);
    const samples = raw.samples.map((sample) => mapDiagnosis(sample, taskId));
    return {
      schemaVersion: raw.schema_version,
      exportedAt: raw.exported_at,
      report: mapReport(raw.report, task, raw.samples.map(mapSample)),
      samples,
      artifact: raw,
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
    const payload = await this.request<RawEvaluationSample>(`/evaluation-jobs/${taskId}/samples/${sampleId}/review`, {
      method: 'PATCH', body: { review_status: reviewStatus },
    });
    return mapSample(payload);
  }
}

export function createApiClient(config: ApiClientConfig): ApiClient {
  return config.mode === 'mock'
    ? new MockApiClient(config.mockDelayMs ?? 180)
    : new HttpApiClient(config.baseUrl, config.fetcher ?? window.fetch.bind(window));
}

const configuredMode = import.meta.env.VITE_API_MODE === 'api' ? 'api' : 'mock';

export const apiMode: ApiMode = configuredMode;
export const apiClient = createApiClient({
  mode: configuredMode,
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
});
