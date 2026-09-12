import { describe, expect, it } from 'vitest';
import { parseDatasetJsonl } from '../../frontend/src/lib/jsonlDataset';

const sample = {
  schema_version: '2.0', sample_id: 'zh-1', question: '退款后成长值如何处理？',
  labels: { reference_answer: '按比例扣回', reference_answers: ['按比例扣回', '依实付金额扣回'] },
  contexts: [{ origin: 'provided', rank: 1, retrieval_run_id: null, doc_id: 'doc-1', chunk_id: 'chunk-1', text: '退款后按实付金额比例扣回成长值。' }],
  metadata: { source: { system: '客服知识库', revision: 2 } },
};

describe('local JSONL preflight', () => {
  it('accepts UTF-8 BOM with LF or CRLF and preserves references and metadata', () => {
    for (const separator of ['\n', '\r\n']) {
      const parsed = parseDatasetJsonl(`\uFEFF${JSON.stringify(sample)}${separator}`);
      expect(parsed.error).toBeNull();
      expect(parsed.samples[0]).toMatchObject({
        question: sample.question,
        labels: { referenceAnswer: '按比例扣回', referenceAnswers: ['按比例扣回', '依实付金额扣回'] },
        metadata: sample.metadata,
      });
    }
  });

  it('rejects an invalid later row with its source line before any caller can write', () => {
    const parsed = parseDatasetJsonl(`${JSON.stringify(sample)}\n{"schema_version":"2.0","sample_id":"bad"}`);
    expect(parsed.samples).toEqual([]);
    expect(parsed.error).toContain('第 2 行');
  });
});
