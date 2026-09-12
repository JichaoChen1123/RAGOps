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

  it('compares semantic content rather than only identifiers', () => {
    expect(sameImportContent(samples, [{ sampleId: 'b', question: 'new' }, { sampleId: 'a', question: 'new' }])).toBe(false);
    expect(sameImportContent(samples, [{ sampleId: 'a', question: '问题 A' }])).toBe(false);
    expect(sameImportContent(samples, [{ sampleId: 'a', question: '问题 A' }, { sampleId: 'a', question: '重复' }])).toBe(false);
  });
});

describe('semantic fingerprint normalization', () => {
  const detailed = [{
    sampleId: 'semantic', question: 'question',
    labels: { referenceAnswer: 'answer', referenceAnswers: ['alternate'], goldDocumentIds: ['doc'], goldEvidenceIds: ['evidence'], expectedDiagnoses: ['retrieval'] },
    contexts: [{ origin: 'provided' as const, rank: 1, docId: 'doc', chunkId: 'chunk', text: 'context', evidenceIds: ['evidence'] }],
    historicalOutput: { answer: 'old', citations: [{ target: 'chunk' }], recordedAt: '2026-01-01T00:00:00Z' }, tags: ['tag'], metadata: { source: { locale: 'zh-CN' } },
  }];

  it('normalizes API defaults but preserves every semantic value', () => {
    const roundTrip = [{ ...detailed[0], contexts: [{ ...detailed[0].contexts[0], rankBefore: null, retrievalRunId: null, score: null, relevanceGrade: null, usefulness: null }] }];
    expect(sameImportContent(detailed, roundTrip)).toBe(true);
    expect(sameImportContent(detailed, [{ ...detailed[0], question: 'changed' }])).toBe(false);
    expect(sameImportContent(detailed, [{ ...detailed[0], labels: { ...detailed[0].labels, referenceAnswers: ['changed'] } }])).toBe(false);
    expect(sameImportContent(detailed, [{ ...detailed[0], contexts: [{ ...detailed[0].contexts[0], text: 'changed' }] }])).toBe(false);
    expect(sameImportContent(detailed, [{ ...detailed[0], metadata: { source: { locale: 'en-US' } } }])).toBe(false);
  });

  it('treats the API compatibility echo for alternate references as one field', () => {
    const input = [{
      sampleId: 'references', question: 'question',
      labels: { referenceAnswer: 'primary', referenceAnswers: ['first', 'second'] },
      metadata: { source: 'cmrc' },
    }];
    const apiRoundTrip = [{
      ...input[0],
      metadata: { source: 'cmrc', reference_answers: ['first', 'second'] },
    }];
    const metadataOnlyLegacy = [{
      ...input[0],
      labels: { referenceAnswer: 'primary', referenceAnswers: [] },
      metadata: { source: 'cmrc', reference_answers: ['first', 'second'] },
    }];

    expect(sameImportContent(input, apiRoundTrip)).toBe(true);
    expect(sameImportContent(input, metadataOnlyLegacy)).toBe(true);
    expect(sameImportContent(input, [{ ...apiRoundTrip[0], labels: { referenceAnswer: 'primary', referenceAnswers: ['second', 'first'] } }])).toBe(false);
  });
});
