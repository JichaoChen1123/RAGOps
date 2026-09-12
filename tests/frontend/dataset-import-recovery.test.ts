import { beforeEach, describe, expect, it } from 'vitest';
import { clearDatasetImportRecovery, loadDatasetImportRecovery, sameImportContent, sampleFingerprint, saveDatasetImportRecovery } from '../../frontend/src/lib/datasetImportRecovery';

const samples = [{ sampleId: 'a', question: '问题 A' }, { sampleId: 'b', question: '问题 B' }];

describe('dataset JSONL import recovery', () => {
  beforeEach(() => { window.localStorage.clear(); });

  it('persists an unfinished draft across a reopened import flow', () => {
    saveDatasetImportRecovery('project-a', { datasetId: 'draft-1', created: true, imported: false, name: '本地集', fileName: '本地.jsonl', fingerprint: sampleFingerprint(samples), samples });
    expect(loadDatasetImportRecovery('project-a')).toMatchObject({ datasetId: 'draft-1', fileName: '本地.jsonl', samples });
    clearDatasetImportRecovery('project-a');
    expect(loadDatasetImportRecovery('project-a')).toBeNull();
  });

  it('only treats the exact saved sample identifiers as a recovered import', () => {
    expect(sameImportContent(samples, [{ sampleId: 'b', question: 'new' }, { sampleId: 'a', question: 'new' }])).toBe(true);
    expect(sameImportContent(samples, [{ sampleId: 'a', question: '问题 A' }])).toBe(false);
    expect(sameImportContent(samples, [{ sampleId: 'a', question: '问题 A' }, { sampleId: 'a', question: '重复' }])).toBe(false);
  });
});
