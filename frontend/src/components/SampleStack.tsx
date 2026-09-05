import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { SampleSummary } from '../types';
import { formatScore } from '../lib/format';
import { CardStack } from './CardStack';
import { StatusBadge } from './StatusBadge';

export function SampleStack({ samples, projectId, taskId }: { samples: SampleSummary[]; projectId: string; taskId: string }) {
  return <CardStack items={samples} label="样本诊断卡片" getLabel={(sample) => sample.sampleId} renderItem={(sample) => <>
    <div className="record-heading"><span className="record-kind">{sample.sampleId}</span>{sample.isMock === true && <em className="mock-label">SIMULATED</em>}</div>
    <h3>{sample.question}</h3>
    <dl className="record-states">
      <div><dt>样本执行</dt><dd><StatusBadge value={sample.runStatus} /></dd></div>
      <div><dt>质量状态</dt><dd><StatusBadge value={sample.qualityStatus} /></dd></div>
      <div><dt>人工复核</dt><dd><StatusBadge value={sample.reviewStatus} /></dd></div>
      <div><dt>延迟</dt><dd>{sample.latencyMs === null ? '未知' : `${sample.latencyMs}ms`}</dd></div>
    </dl>
    <div className="sample-answers"><div><span>参考答案</span><p>{sample.referenceAnswer ?? '未知'}</p></div><div><span>本次回答</span><p>{sample.generatedAnswer ?? '未知 / 未产生回答'}</p></div></div>
    <dl className="record-details sample-scores">
      <div><dt>Recall@5</dt><dd>{formatScore(sample.recallAt5, sample.recallAt5Status)}</dd></div>
      <div><dt>忠实性</dt><dd>{formatScore(sample.faithfulness, sample.faithfulnessStatus)}</dd></div>
      <div><dt>引用支持</dt><dd>{formatScore(sample.citationSupportRate, sample.citationSupportStatus)}</dd></div>
    </dl>
    {sample.error && <p className="text-critical">{sample.error.code} · {sample.error.message}</p>}
    <footer className="record-footer"><span>{sample.contexts.length} 条上下文 · {sample.citations.length} 条引用</span><Link aria-label={`诊断样本 ${sample.id}`} className="button button-secondary" to={`/projects/${projectId}/evaluations/${taskId}/samples/${sample.id}`}>诊断 <ArrowRight size={16} /></Link></footer>
  </>} />;
}
