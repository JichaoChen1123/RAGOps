import type { DatasetContextInput, DatasetSampleInput } from '../types';

export type JsonlValidation = { samples: DatasetSampleInput[]; error: string | null };

const object = (value: unknown): Record<string, unknown> | null => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
const strings = (value: unknown, field: string, line: number): string[] => {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) throw new Error(`第 ${line} 行：${field} 必须是字符串数组`);
  return value;
};

function sampleFromLine(value: unknown, line: number): DatasetSampleInput {
  const row = object(value);
  if (!row) throw new Error(`第 ${line} 行：必须是 JSON 对象`);
  const allowed = new Set(['schema_version', 'sample_id', 'question', 'labels', 'contexts', 'historical_output', 'tags', 'metadata']);
  const unexpected = Object.keys(row).find((key) => !allowed.has(key));
  if (unexpected) throw new Error(`第 ${line} 行：不支持字段 ${unexpected}`);
  if (row.schema_version !== '2.0') throw new Error(`第 ${line} 行：schema_version 必须为 2.0`);
  if (typeof row.sample_id !== 'string' || !row.sample_id.trim()) throw new Error(`第 ${line} 行：sample_id 不能为空`);
  if (typeof row.question !== 'string' || !row.question.trim()) throw new Error(`第 ${line} 行：question 不能为空`);
  const labelsRaw = row.labels === undefined ? {} : object(row.labels);
  if (!labelsRaw) throw new Error(`第 ${line} 行：labels 必须是对象`);
  const labelAllowed = new Set(['reference_answer', 'reference_answers', 'gold_document_ids', 'gold_evidence_ids', 'expected_diagnoses']);
  const extraLabel = Object.keys(labelsRaw).find((key) => !labelAllowed.has(key));
  if (extraLabel) throw new Error(`第 ${line} 行：labels 不支持字段 ${extraLabel}`);
  const referenceAnswer = labelsRaw.reference_answer;
  if (referenceAnswer !== undefined && referenceAnswer !== null && typeof referenceAnswer !== 'string') throw new Error(`第 ${line} 行：labels.reference_answer 必须是字符串或 null`);
  const referenceAnswers = labelsRaw.reference_answers === undefined ? undefined : strings(labelsRaw.reference_answers, 'labels.reference_answers', line);
  const contextsRaw = row.contexts === undefined ? [] : row.contexts;
  if (!Array.isArray(contextsRaw)) throw new Error(`第 ${line} 行：contexts 必须是数组`);
  const contexts = contextsRaw.map((item, index) => {
    const context = object(item);
    if (!context || typeof context.origin !== 'string' || typeof context.rank !== 'number' || typeof context.doc_id !== 'string' || typeof context.chunk_id !== 'string' || typeof context.text !== 'string') throw new Error(`第 ${line} 行：contexts[${index}] 缺少 v2 必填字段`);
    return { origin: context.origin as DatasetContextInput['origin'], rank: context.rank, rankBefore: typeof context.rank_before === 'number' ? context.rank_before : null, retrievalRunId: typeof context.retrieval_run_id === 'string' ? context.retrieval_run_id : null, docId: context.doc_id, chunkId: context.chunk_id, evidenceIds: context.evidence_ids === undefined ? [] : strings(context.evidence_ids, `contexts[${index}].evidence_ids`, line), text: context.text, score: typeof context.score === 'number' ? context.score : null, relevanceGrade: typeof context.relevance_grade === 'number' ? context.relevance_grade : null, usefulness: typeof context.usefulness === 'boolean' ? context.usefulness : null };
  });
  if (contexts.map((item) => item.rank).some((rank, index) => rank !== index + 1)) throw new Error(`第 ${line} 行：contexts.rank 必须从 1 连续排序`);
  if (row.tags !== undefined) strings(row.tags, 'tags', line);
  if (row.metadata !== undefined && !object(row.metadata)) throw new Error(`第 ${line} 行：metadata 必须是对象`);
  const historical = row.historical_output === undefined || row.historical_output === null ? null : object(row.historical_output);
  if (historical && (typeof historical.answer !== 'string' || typeof historical.recorded_at !== 'string' || !Array.isArray(historical.citations))) throw new Error(`第 ${line} 行：historical_output 缺少 answer、citations 或 recorded_at`);
  return { sampleId: row.sample_id.trim(), question: row.question.trim(), labels: { referenceAnswer: referenceAnswer ?? null, referenceAnswers, goldDocumentIds: labelsRaw.gold_document_ids === undefined ? [] : strings(labelsRaw.gold_document_ids, 'labels.gold_document_ids', line), goldEvidenceIds: labelsRaw.gold_evidence_ids === undefined ? [] : strings(labelsRaw.gold_evidence_ids, 'labels.gold_evidence_ids', line), expectedDiagnoses: labelsRaw.expected_diagnoses === undefined ? [] : strings(labelsRaw.expected_diagnoses, 'labels.expected_diagnoses', line) }, contexts, historicalOutput: historical ? { answer: historical.answer as string, citations: historical.citations as Array<Record<string, unknown>>, recordedAt: historical.recorded_at as string } : null, tags: row.tags === undefined ? [] : strings(row.tags, 'tags', line), metadata: row.metadata as Record<string, unknown> ?? {} };
}

export function parseDatasetJsonl(text: string): JsonlValidation {
  try {
    const samples: DatasetSampleInput[] = [];
    const ids = new Set<string>();
    text.replace(/^\uFEFF/, '').split(/\r?\n/).forEach((raw, index) => {
      if (!raw.trim()) return;
      let value: unknown;
      try { value = JSON.parse(raw); } catch { throw new Error(`第 ${index + 1} 行：不是有效 JSON`); }
      const sample = sampleFromLine(value, index + 1);
      if (ids.has(sample.sampleId)) throw new Error(`第 ${index + 1} 行：sample_id 重复（${sample.sampleId}）`);
      ids.add(sample.sampleId); samples.push(sample);
    });
    if (!samples.length) throw new Error('文件中没有可导入的 JSONL 样本');
    return { samples, error: null };
  } catch (error) { return { samples: [], error: error instanceof Error ? error.message : '文件校验失败' }; }
}
