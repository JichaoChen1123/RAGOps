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

export const sampleFingerprint = (samples: DatasetSampleInput[]) => samples.map((sample) => sample.sampleId).sort().join('|');

export function sameImportContent(expected: DatasetSampleInput[], actual: DatasetSampleInput[]) {
  const actualIds = new Set(actual.map((sample) => sample.sampleId));
  return expected.length === actualIds.size && expected.every((sample) => actualIds.has(sample.sampleId));
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
