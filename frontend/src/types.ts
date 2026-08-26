export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed';
export type DatasetStatus = 'ready' | 'indexing' | 'draft' | 'failed';
export type Severity = 'critical' | 'warning' | 'healthy' | 'unknown';
export type ViewScenario = 'normal' | 'loading' | 'empty' | 'error' | 'partial';

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
  reviewStatus: 'pending' | 'confirmed' | 'dismissed';
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
  listEvaluationTasks(projectId: string): Promise<EvaluationTask[]>;
  getEvaluationReport(projectId: string, taskId: string): Promise<EvaluationReport>;
  getSampleDiagnosis(projectId: string, taskId: string, sampleId: string): Promise<SampleDiagnosis>;
}
