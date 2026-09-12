import type { DatasetSampleInput } from '../types';

export type DatasetImportRecovery = {
  datasetId: string;
  created: boolean;
  imported: boolean;
  name: string;
  fileName: string;
  fingerprint: string;
  samples: DatasetSampleInput[];
};

const key = (projectId: string) => `ragops.dataset-import-recovery.${projectId}`;

/**
 * The API normalizes absent import fields to these values.  Treating those
 * representations as equivalent makes a response round-trip comparable to the
 * JSONL the user selected, while every supplied value remains significant.
 */
function normalizedReferenceAnswers(sample: DatasetSampleInput): string[] {
  const labels = sample.labels?.referenceAnswers;
  if (labels && labels.length > 0) return labels;
  const metadataReferences = sample.metadata?.reference_answers;
  return Array.isArray(metadataReferences)
    ? metadataReferences.filter((answer): answer is string => typeof answer === 'string')
    : [];
}

function normalizeSample(sample: DatasetSampleInput) {
  // The API stores v2 alternate references in labels and, for compatibility,
  // echoes them in metadata.reference_answers.  It is one logical field, not
  // two independent values, so normalize both representations before deciding
  // whether a draft can safely be resumed.
  const { reference_answers: _derivedReferenceAnswers, ...metadata } = sample.metadata ?? {};
  return {
    sampleId: sample.sampleId,
    question: sample.question,
    labels: {
      referenceAnswer: sample.labels?.referenceAnswer ?? null,
      referenceAnswers: normalizedReferenceAnswers(sample),
      goldDocumentIds: sample.labels?.goldDocumentIds ?? [],
      goldEvidenceIds: sample.labels?.goldEvidenceIds ?? [],
      expectedDiagnoses: sample.labels?.expectedDiagnoses ?? [],
    },
    contexts: (sample.contexts ?? []).map((context) => ({
      origin: context.origin,
      rank: context.rank,
      rankBefore: context.rankBefore ?? null,
      retrievalRunId: context.retrievalRunId ?? null,
      docId: context.docId,
      chunkId: context.chunkId,
      evidenceIds: context.evidenceIds ?? [],
      text: context.text,
      score: context.score ?? null,
      relevanceGrade: context.relevanceGrade ?? null,
      usefulness: context.usefulness ?? null,
    })),
    historicalOutput: sample.historicalOutput ?? null,
    tags: sample.tags ?? [],
    metadata,
  };
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(',')}]`;
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

const normalizedImport = (samples: DatasetSampleInput[]) => samples
  .map(normalizeSample)
  .map(stableJson)
  .sort();

/** A deterministic content key shared by recovery selection and server checks. */
export const sampleFingerprint = (samples: DatasetSampleInput[]) => stableJson(normalizedImport(samples));

export function sameImportContent(expected: DatasetSampleInput[], actual: DatasetSampleInput[]) {
  return sampleFingerprint(expected) === sampleFingerprint(actual);
}

export function loadDatasetImportRecovery(projectId: string): DatasetImportRecovery | null {
  try {
    const value = window.localStorage.getItem(key(projectId));
    if (!value) return null;
    const parsed = JSON.parse(value) as DatasetImportRecovery;
    return parsed.datasetId && Array.isArray(parsed.samples) ? parsed : null;
  } catch { return null; }
}

export function saveDatasetImportRecovery(projectId: string, recovery: DatasetImportRecovery) {
  window.localStorage.setItem(key(projectId), JSON.stringify(recovery));
}

export function clearDatasetImportRecovery(projectId: string) {
  window.localStorage.removeItem(key(projectId));
}
