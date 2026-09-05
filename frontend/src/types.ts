export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type ExecutionOutcome = 'succeeded' | 'partial_failed' | 'failed' | null;
export type QualityStatus = 'not_evaluated' | 'evaluated' | 'partial' | 'error' | 'legacy_unknown';
export type QualityVerdict = 'passed' | 'failed' | 'unknown';
export type MetricStatus = 'ok' | 'not_evaluated' | 'not_applicable' | 'unknown' | 'error' | 'legacy';
export type DatasetStatus = 'ready' | 'indexing' | 'draft' | 'failed';
export type Severity = 'critical' | 'warning' | 'healthy' | 'unknown';
export type ViewScenario = 'normal' | 'loading' | 'empty' | 'error' | 'partial';
export type SampleReviewStatus = 'pending' | 'confirmed' | 'dismissed';
export type ContextOrigin = 'provided' | 'retrieved' | 'legacy_unknown';
export type ProviderConfigurationStatus = 'not_configured' | 'configured_unverified' | 'verified' | 'unknown';

export interface MetricValue {
  key: string;
  label: string;
  value: number | boolean | null;
  status: MetricStatus;
  unit?: '%' | 'ms' | 'USD';
  delta?: number | null;
  direction?: 'higher' | 'lower';
  threshold?: number;
  evaluatedCount?: number | null;
  excludedCount?: number | null;
  details?: Record<string, unknown>;
}

export interface ProjectOverview {
  project: {
    id: string;
    name: string;
    description: string;
    environment: string;
    updatedAt: string;
  };
  metrics: MetricValue[];
  recentTasks: EvaluationTask[];
  failureDistribution: FailureBucket[];
  trend: TrendPoint[];
  warnings?: string[];
}

export interface Dataset {
  id: string;
  name: string;
  description: string;
  sampleCount: number;
  status: DatasetStatus;
  schemaVersion: string;
  version: string;
  contentSha256: string | null;
  coverage: number | null;
  updatedAt: string;
  owner: string;
}

export interface PromptSnapshot {
  version: string;
  text: string;
}

export interface GenerationConfig {
  model: string;
  temperature: number;
  topP: number;
  maxOutputTokens: number;
  stop: string[];
  seed: number | null;
}

export interface ExecutionSnapshot {
  contractVersion: string;
  adapterId: string;
  providerId: string | null;
  prompt: PromptSnapshot;
  generation: GenerationConfig;
  contextPolicy: 'dataset_contexts' | 'none' | 'retrieval';
  dataset: {
    id: string;
    version: string;
    schemaVersion: string;
    contentSha256: string | null;
  };
  metricConfig: Array<Record<string, unknown>>;
  qualityGate: Record<string, unknown> | null;
  externalCallsEnabledAtCreation: boolean;
  createdAt: string;
  configVersion: string;
}

export interface EvaluationTask {
  id: string;
  name: string;
  datasetId: string;
  datasetName: string;
  status: TaskStatus;
  outcome: ExecutionOutcome;
  qualityStatus: QualityStatus;
  qualityVerdict: QualityVerdict;
  qualityScore: number | null;
  progress: number;
  createdAt: string;
  completedAt: string | null;
  modelVersion: string | null;
  promptVersion: string | null;
  adapterId: string | null;
  providerId: string | null;
  isMock: boolean | null;
  totalSamples: number;
  succeededSamples: number;
  failedSamples: number;
  schemaVersion: string;
  executionSnapshot: ExecutionSnapshot | null;
  failureCode?: string | null;
  failureMessage?: string | null;
}

export interface FailureBucket {
  key: string;
  label: string;
  count: number;
  severity: Severity;
}

export interface TrendPoint {
  label: string;
  score: number;
  latencyMs: number;
}

export interface ExecutionSummary {
  outcome: ExecutionOutcome;
  totalCount: number;
  succeededCount: number;
  failedCount: number;
  successRate: number | null;
}

export interface QualitySummary {
  status: QualityStatus;
  verdict: QualityVerdict;
  score: number | null;
  evaluatedSampleCount: number | null;
}

export interface EvaluationReport {
  id: string;
  schemaVersion: string;
  task: EvaluationTask;
  verdict: 'passed' | 'failed' | 'undetermined';
  verdictReason: string;
  executionSummary: ExecutionSummary;
  qualitySummary: QualitySummary;
  executionSnapshot: ExecutionSnapshot | null;
  isSimulated: boolean | null;
  metrics: MetricValue[];
  failures: FailureBucket[];
  samples: SampleSummary[];
  generatedAt: string | null;
  baselineLabel: string | null;
  warnings?: string[];
}

export interface ModelErrorSummary {
  code: string;
  message: string;
  retryable: boolean;
  attempts: number;
  providerRequestId: string | null;
  retryAfterMs: number | null;
}

export interface ContextEvidence {
  key: string;
  origin: ContextOrigin;
  rank: number | null;
  rankBefore: number | null;
  retrievalRunId: string | null;
  docId: string | null;
  chunkId: string | null;
  evidenceIds: string[];
  text: string;
  score: number | null;
  relevanceGrade: number | null;
  usefulness: boolean | null;
  title: string | null;
  source: string | null;
  isExpected: boolean;
}

export interface CitationEvidence {
  id: string;
  marker: string;
  claimId: string | null;
  raw: string;
  targetType: 'context_item' | 'document' | 'external' | null;
  targetId: string | null;
  resolved: boolean | null;
  supportsClaim: boolean | null;
  supportJudgeVersion: string | null;
}

export interface SampleSummary {
  id: string;
  sampleId: string;
  question: string;
  referenceAnswer: string | null;
  historicalAnswer: string | null;
  generatedAnswer: string | null;
  failureType: string;
  severity: Severity;
  recallAt5: number | null;
  recallAt5Status: MetricStatus;
  faithfulness: number | null;
  faithfulnessStatus: MetricStatus;
  citationSupportRate: number | null;
  citationSupportStatus: MetricStatus;
  latencyMs: number | null;
  runStatus: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'legacy_unknown';
  qualityStatus: QualityStatus;
  reviewStatus: SampleReviewStatus;
  contexts: ContextEvidence[];
  citations: CitationEvidence[];
  error: ModelErrorSummary | null;
  isMock: boolean | null;
}

export interface DatasetSampleLabelsInput {
  referenceAnswer?: string | null;
  goldDocumentIds?: string[];
  goldEvidenceIds?: string[];
  expectedDiagnoses?: string[];
}

export interface DatasetContextInput {
  origin: ContextOrigin;
  rank: number;
  rankBefore?: number | null;
  retrievalRunId?: string | null;
  docId: string;
  chunkId: string;
  evidenceIds?: string[];
  text: string;
  score?: number | null;
  relevanceGrade?: number | null;
  usefulness?: boolean | null;
}

export interface DatasetSampleInput {
  sampleId: string;
  question: string;
  labels?: DatasetSampleLabelsInput;
  contexts?: DatasetContextInput[];
  historicalOutput?: {
    answer: string;
    citations: Array<Record<string, unknown>>;
    recordedAt: string;
  } | null;
  tags?: string[];
  metadata?: Record<string, unknown>;
}

export interface DatasetCreateInput {
  name: string;
  description?: string;
  owner: string;
  version?: string;
  samples?: DatasetSampleInput[];
}

export interface DatasetImportResult {
  accepted: number;
  rejected: number;
  dataset: Dataset;
}

export interface EvaluationTaskCreateInput {
  datasetId: string;
  name?: string;
  adapterId: 'mock' | 'openai_compatible';
  prompt: PromptSnapshot;
  generation: GenerationConfig;
  contextPolicy: 'dataset_contexts' | 'none' | 'retrieval';
  metrics?: Array<{ name: string; version: string; parameters: Record<string, unknown> }>;
  qualityGate?: Record<string, unknown> | null;
}

export interface ReportExport {
  schemaVersion: string;
  exportedAt: string;
  report: EvaluationReport;
  samples: SampleDiagnosis[];
  artifact: unknown;
}

export interface DiagnosisRule {
  label: string;
  confidence: number | null;
  severity: Severity;
  explanation: string;
  evidenceIds: string[];
}

export interface SampleRunDetail {
  runId: string | null;
  status: SampleSummary['runStatus'];
  adapterId: string | null;
  providerId: string | null;
  requestedModel: string | null;
  actualModel: string | null;
  isMock: boolean | null;
  finishReason: string | null;
  latencyMs: number | null;
  usage: { inputTokens: number; outputTokens: number; totalTokens: number } | null;
  cost: number | null;
  providerRequestId: string | null;
  attemptCount: number | null;
  error: ModelErrorSummary | null;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface SampleDiagnosis {
  id: string;
  sampleId: string;
  taskId: string;
  question: string;
  expectedAnswer: string | null;
  historicalAnswer: string | null;
  generatedAnswer: string | null;
  metrics: MetricValue[];
  qualityStatus: QualityStatus;
  primaryDiagnosis: DiagnosisRule;
  secondaryDiagnoses: DiagnosisRule[];
  contexts: ContextEvidence[];
  citations: CitationEvidence[];
  run: SampleRunDetail;
  reviewStatus: SampleReviewStatus;
  traceId: string | null;
  evaluatedAt: string | null;
  warnings?: string[];
}

export interface AdapterCapabilities {
  externalNetwork: boolean;
  supportsSeed: boolean;
  supportsStop: boolean;
  reportsUsage: boolean;
  reportsRequestId: boolean;
}

export interface ProviderStatus {
  providerId: string | null;
  configurationStatus: ProviderConfigurationStatus;
  baseUrlConfigured: boolean | null;
  credentialConfigured: boolean | null;
  defaultModelConfigured: boolean | null;
  lastVerifiedAt: string | null;
  verificationMessage: string | null;
}

export interface ModelExecutionStatus {
  schemaVersion: string;
  backendExecutionAdapter: string | null;
  externalCallsEnabled: boolean | null;
  executionAvailable: boolean | null;
  activeAdapter: {
    adapterId: string;
    isMock: boolean | null;
    capabilities: AdapterCapabilities;
  } | null;
  providers: ProviderStatus[];
  source: 'api' | 'fixture';
}

export interface ApiClient {
  getProjectOverview(projectId: string): Promise<ProjectOverview>;
  getModelExecutionStatus(): Promise<ModelExecutionStatus>;
  listDatasets(projectId: string): Promise<Dataset[]>;
  createDataset(projectId: string, input: DatasetCreateInput): Promise<Dataset>;
  importDatasetSamples(projectId: string, datasetId: string, samples: DatasetSampleInput[]): Promise<DatasetImportResult>;
  publishDataset(projectId: string, datasetId: string): Promise<Dataset>;
  listEvaluationTasks(projectId: string): Promise<EvaluationTask[]>;
  createEvaluationTask(projectId: string, input: EvaluationTaskCreateInput): Promise<EvaluationTask>;
  getEvaluationReport(projectId: string, taskId: string): Promise<EvaluationReport>;
  exportEvaluationReport(projectId: string, taskId: string): Promise<ReportExport>;
  getSampleDiagnosis(projectId: string, taskId: string, sampleId: string): Promise<SampleDiagnosis>;
  updateSampleReview(
    projectId: string,
    taskId: string,
    sampleId: string,
    reviewStatus: SampleReviewStatus,
  ): Promise<SampleSummary>;
}
