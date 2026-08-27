export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed';
export type DatasetStatus = 'ready' | 'indexing' | 'draft' | 'failed';
export type Severity = 'critical' | 'warning' | 'healthy' | 'unknown';
export type ViewScenario = 'normal' | 'loading' | 'empty' | 'error' | 'partial';
export type SampleReviewStatus = 'pending' | 'confirmed' | 'dismissed';

export interface MetricValue {
  key: string;
  label: string;
  value: number | null;
  unit?: '%' | 'ms' | 'USD';
  delta?: number | null;
  direction?: 'higher' | 'lower';
  threshold?: number;
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
  version: string;
  coverage: number;
  updatedAt: string;
  owner: string;
}

export interface EvaluationTask {
  id: string;
  name: string;
  datasetId: string;
  datasetName: string;
  status: TaskStatus;
  progress: number;
  createdAt: string;
  completedAt?: string;
  modelVersion: string;
  promptVersion: string;
  totalSamples: number;
  failedSamples?: number;
  score?: number;
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

export interface EvaluationReport {
  id: string;
  task: EvaluationTask;
  verdict: 'passed' | 'failed' | 'undetermined';
  verdictReason: string;
  metrics: MetricValue[];
  failures: FailureBucket[];
  samples: SampleSummary[];
  generatedAt: string;
  baselineLabel: string;
  warnings?: string[];
}

export interface SampleSummary {
  id: string;
  question: string;
  failureType: string;
  severity: Severity;
  recallAt5: number | null;
  faithfulness: number | null;
  citationHitRate: number | null;
  latencyMs: number;
  reviewStatus: SampleReviewStatus;
}

export interface DatasetSampleInput {
  sampleId: string;
  question: string;
  referenceAnswer?: string;
  tags?: string[];
}

export interface DatasetCreateInput {
  name: string;
  description?: string;
  owner: string;
  version?: string;
  samples?: DatasetSampleInput[];
}

export interface EvaluationTaskCreateInput {
  datasetId: string;
  name?: string;
  modelVersion: string;
  promptVersion: string;
}

export interface ReportExport {
  schemaVersion: '1.0';
  exportedAt: string;
  report: EvaluationReport;
}

export interface RetrievedDocument {
  id: string;
  rank: number;
  title: string;
  source: string;
  score: number;
  isExpected: boolean;
  snippet: string;
  chunkId: string;
}

export interface CitationEvidence {
  id: string;
  marker: string;
  documentId: string;
  claim: string;
  supported: boolean;
}

export interface DiagnosisRule {
  label: string;
  confidence: number | null;
  severity: Severity;
  explanation: string;
  evidenceIds: string[];
}

export interface SampleDiagnosis {
  id: string;
  taskId: string;
  question: string;
  expectedAnswer: string;
  generatedAnswer: string;
  metrics: MetricValue[];
  primaryDiagnosis: DiagnosisRule;
  secondaryDiagnoses: DiagnosisRule[];
  retrievedDocuments: RetrievedDocument[];
  citations: CitationEvidence[];
  traceId: string;
  evaluatedAt: string;
  warnings?: string[];
}

export interface ApiClient {
  getProjectOverview(projectId: string): Promise<ProjectOverview>;
  listDatasets(projectId: string): Promise<Dataset[]>;
  createDataset(projectId: string, input: DatasetCreateInput): Promise<Dataset>;
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
