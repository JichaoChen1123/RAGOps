import { ArrowLeft, Check, ChevronRight, ClipboardCheck, Copy, ExternalLink, SearchX, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { apiClient, apiMode } from '../api/client';
import { Dialog, Toast } from '../components/Interaction';
import { MetricCard } from '../components/MetricCard';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { copyText } from '../lib/browser';
import { formatDateTime } from '../lib/format';
import type { CitationEvidence, ContextEvidence, SampleDiagnosis, SampleReviewStatus } from '../types';

const emptyDiagnosis = (taskId: string, sampleId: string): SampleDiagnosis => ({
  id: sampleId,
  sampleId,
  taskId,
  question: '',
  expectedAnswer: null,
  historicalAnswer: null,
  generatedAnswer: null,
  metrics: [],
  qualityStatus: 'not_evaluated',
  primaryDiagnosis: { label: '不可判定', confidence: null, severity: 'unknown', explanation: '样本缺少诊断输入。', evidenceIds: [] },
  secondaryDiagnoses: [],
  contexts: [],
  citations: [],
  run: {
    runId: null,
    status: 'legacy_unknown',
    adapterId: null,
    providerId: null,
    requestedModel: null,
    actualModel: null,
    isMock: null,
    finishReason: null,
    latencyMs: null,
    usage: null,
    cost: null,
    providerRequestId: null,
    attemptCount: null,
    error: null,
    startedAt: null,
    finishedAt: null,
  },
  reviewStatus: 'pending',
  traceId: null,
  evaluatedAt: null,
});

const originLabel = (origin: ContextEvidence['origin']) => origin === 'retrieved'
  ? '本次检索'
  : origin === 'provided' ? '给定上下文' : '来源未知';

const citationLabel = (citation: CitationEvidence) => citation.supportsClaim === true
  ? '已判定支持'
  : citation.supportsClaim === false ? '已判定不支持'
    : citation.resolved === true ? '已解析 · 支持性未评估'
      : citation.resolved === false ? '未解析' : '解析与支持性未知';

export function DiagnosisPage() {
  const { projectId = 'demo', taskId = '', sampleId = '' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const { state, retry } = useApiResource(
    () => apiClient.getSampleDiagnosis(projectId, taskId, sampleId),
    [projectId, taskId, sampleId],
    {
      scenario,
      emptyValue: emptyDiagnosis(taskId, sampleId),
      partialize: (data) => ({
        ...data,
        metrics: data.metrics.map((metric, index) => index > 1 ? { ...metric, value: null, status: 'not_evaluated' as const } : metric),
        citations: data.citations.slice(0, 1),
        warnings: [...(data.warnings ?? []), '引用记录仅返回部分数据。'],
      }),
    },
  );
  const [selectedContextKey, setSelectedContextKey] = useState<string | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [reviewStatus, setReviewStatus] = useState<SampleReviewStatus>('pending');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [savingReview, setSavingReview] = useState(false);

  useEffect(() => {
    if (state.status === 'success') setReviewStatus(state.data.reviewStatus);
  }, [state]);

  const selectedContext = useMemo(() => state.status === 'success'
    ? state.data.contexts.find((context) => context.key === selectedContextKey) ?? state.data.contexts[0]
    : undefined, [selectedContextKey, state]);

  if (state.status === 'loading') return <LoadingState label="正在还原样本证据链" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  const diagnosis = state.data;

  if (!diagnosis.question) {
    return <><Link className="back-link" to={`/projects/${projectId}/evaluations/${taskId}/report`}><ArrowLeft size={15} />返回评测报告</Link><EmptyState title="样本没有诊断数据" description="当前样本缺少原始问题，无法展示运行与证据记录。" /></>;
  }

  const selectCitation = (citation: CitationEvidence) => {
    const match = diagnosis.contexts.find((context) => context.docId === citation.targetId || context.chunkId === citation.targetId);
    if (!match) {
      setFeedback(`引用目标 ${citation.targetId || '未知'} 未对应到当前上下文记录`);
      return;
    }
    setSelectedContextKey(match.key);
    document.getElementById('evidence-detail')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  const copyAnswer = async () => {
    if (diagnosis.generatedAnswer === null) return;
    try {
      await copyText(diagnosis.generatedAnswer);
      setFeedback('已复制本次回答');
    } catch {
      setFeedback('复制失败，请手动选择本次回答');
    }
  };

  const updateReview = async (next: 'confirmed' | 'dismissed') => {
    setSavingReview(true);
    try {
      const updated = await apiClient.updateSampleReview(projectId, taskId, sampleId, next);
      setReviewStatus(updated.reviewStatus);
      const suffix = apiMode === 'mock' ? '（仅当前页面会话）' : '（已写入 API）';
      setFeedback(next === 'confirmed' ? `已确认故障归因${suffix}` : `已排除本次诊断${suffix}`);
    } catch (error) {
      setFeedback(error instanceof Error ? `复核更新失败：${error.message}` : '复核更新失败，请稍后重试');
    } finally {
      setSavingReview(false);
    }
  };

  return (
    <>
      <div className="diagnosis-nav">
        <Link className="back-link" to={`/projects/${projectId}/evaluations/${taskId}/report`}><ArrowLeft size={15} />返回评测报告</Link>
        <span>样本 {diagnosis.sampleId} · {diagnosis.evaluatedAt ? formatDateTime(diagnosis.evaluatedAt) : '时间未知'} · <code>{diagnosis.traceId ?? 'run ID 未知'}</code></span>
      </div>
      <PartialDataBanner message={state.partialMessage} />
      {diagnosis.warnings?.map((warning) => <PartialDataBanner key={warning} message={warning} />)}
      {diagnosis.run.isMock === true && <div className="simulation-banner" role="note"><strong>SIMULATED RUN</strong><span>本次回答、上下文与诊断来自离线模拟记录，不代表真实模型或提供方连接已验证。</span></div>}
      <section className="question-card">
        <span className="eyebrow">ORIGINAL QUESTION</span><h2>{diagnosis.question}</h2>
        <div className="diagnosis-metrics">{diagnosis.metrics.map((metric) => <MetricCard compact key={metric.key} metric={metric} />)}</div>
      </section>
      <section className="diagnosis-callout">
        <div className="diagnosis-symbol"><SearchX size={21} /></div>
        <div><span>主要疑似原因</span><h3>{diagnosis.primaryDiagnosis.label}</h3><p>{diagnosis.primaryDiagnosis.explanation}</p></div>
        <div className="confidence"><small>置信度</small><strong>{diagnosis.primaryDiagnosis.confidence === null ? '未知' : `${Math.round(diagnosis.primaryDiagnosis.confidence * 100)}%`}</strong><StatusBadge value={diagnosis.primaryDiagnosis.severity} /></div>
      </section>
      <div className="evidence-layout">
        <section className="evidence-column">
          <header><span>01</span><div><strong>上下文与来源</strong><small>给定、检索与旧来源未知严格区分</small></div></header>
          <div className="document-list">
            {diagnosis.contexts.length === 0 && <EmptyState title="没有上下文记录" description="不能据缺失数据假定执行过检索。" />}
            {diagnosis.contexts.map((context) => (
              <button className={`document-item ${selectedContext?.key === context.key ? 'selected' : ''} ${context.isExpected ? 'expected' : ''}`} type="button" key={context.key} onClick={() => setSelectedContextKey(context.key)}>
                <span className="rank">#{context.rank ?? '未知'}</span><span className="document-copy"><strong>{context.title ?? context.docId ?? '文档标识未知'}</strong><small>{originLabel(context.origin)} · {context.source ?? context.docId ?? '来源标识未知'}</small><em>{context.text || '片段内容未知'}</em></span>
                <span className="document-score"><strong>{context.score === null ? '未知' : context.score.toFixed(2)}</strong><small>来源分数</small>{context.isExpected && <i>参考标签</i>}</span>
              </button>
            ))}
          </div>
        </section>
        <section className="answer-column">
          <header><span>02</span><div><strong>回答与引用</strong><small>参考、历史与本次输出分别展示</small></div></header>
          <div className="answer-block expected-answer"><span>参考答案（评测标签）</span><p>{diagnosis.expectedAnswer ?? '未知 / 未提供'}</p></div>
          {diagnosis.historicalAnswer !== null && <div className="answer-block historical-answer"><span>导入前历史回答</span><p>{diagnosis.historicalAnswer}</p></div>}
          <div className="answer-block generated-answer">
            <span>本次运行回答 <button type="button" aria-label="复制模型回答" disabled={diagnosis.generatedAnswer === null} onClick={() => void copyAnswer()}><Copy size={13} /></button></span><p>{diagnosis.generatedAnswer ?? '未知 / 本次运行未产生回答'}</p>
            <div className="citation-list">{diagnosis.citations.length === 0 && <span className="unknown-value">没有引用记录</span>}{diagnosis.citations.map((citation) => <button key={citation.id} className={`citation-chip citation-${citation.supportsClaim === true ? 'supported' : citation.supportsClaim === false ? 'unsupported' : 'unknown'}`} type="button" onClick={() => selectCitation(citation)}>{citation.marker} {citation.supportsClaim === true ? <Check size={13} /> : citation.supportsClaim === false ? <X size={13} /> : null} {citationLabel(citation)} <ChevronRight size={13} /></button>)}</div>
          </div>
          {diagnosis.run.error && <div className="run-error" role="alert"><strong>{diagnosis.run.error.code}</strong><p>{diagnosis.run.error.message}</p><small>尝试 {diagnosis.run.error.attempts} 次 · {diagnosis.run.error.retryable ? '可重试' : '不可自动重试'}</small></div>}
          {diagnosis.secondaryDiagnoses.map((item) => <div className="secondary-diagnosis" key={item.label}><StatusBadge value={item.severity} /><div><strong>{item.label}</strong><p>{item.explanation}</p></div></div>)}
        </section>
      </div>
      <section className="run-metadata" aria-label="本次运行元信息">
        <header><span className="eyebrow">RUN METADATA</span><h3>本次运行与用量</h3></header>
        <dl className="detail-list">
          <div><dt>执行 / 质量状态</dt><dd><StatusBadge value={diagnosis.run.status} /> <StatusBadge value={diagnosis.qualityStatus} /></dd></div>
          <div><dt>执行器 / 提供方</dt><dd><code>{diagnosis.run.adapterId ?? '未知'}</code> / <code>{diagnosis.run.providerId ?? '无或未知'}</code></dd></div>
          <div><dt>请求 / 实际模型</dt><dd><code>{diagnosis.run.requestedModel ?? '未知'}</code> / <code>{diagnosis.run.actualModel ?? '未知'}</code></dd></div>
          <div><dt>Token 用量</dt><dd>{diagnosis.run.usage ? `${diagnosis.run.usage.inputTokens} 输入 / ${diagnosis.run.usage.outputTokens} 输出 / ${diagnosis.run.usage.totalTokens} 总计` : '未知'}</dd></div>
          <div><dt>成本 / 延迟</dt><dd>{diagnosis.run.cost === null ? '成本未知' : `$${diagnosis.run.cost}`} · {diagnosis.run.latencyMs === null ? '延迟未知' : `${diagnosis.run.latencyMs}ms`}</dd></div>
          <div><dt>完成原因 / 尝试</dt><dd>{diagnosis.run.finishReason ?? '未知'} / {diagnosis.run.attemptCount ?? '未知'}</dd></div>
        </dl>
      </section>
      {selectedContext && (
        <section className="evidence-detail" id="evidence-detail">
          <header><div><span className="eyebrow">CONTEXT DETAIL · {originLabel(selectedContext.origin).toUpperCase()}</span><h3>{selectedContext.title ?? selectedContext.docId ?? '文档标识未知'}</h3></div><button className="button button-secondary" type="button" onClick={() => setSourceOpen(true)}><ExternalLink size={14} />打开源文档</button></header>
          <div className="evidence-meta"><span>Rank <strong>#{selectedContext.rank ?? '未知'}</strong></span><span>Doc <code>{selectedContext.docId ?? '未知'}</code></span><span>Chunk <code>{selectedContext.chunkId ?? '未知'}</code></span><span>Score <strong>{selectedContext.score === null ? '未知' : selectedContext.score.toFixed(2)}</strong></span><span>检索运行 <code>{selectedContext.retrievalRunId ?? '无'}</code></span></div>
          <blockquote>{selectedContext.text || '片段内容未知'}</blockquote>
        </section>
      )}
      <div className="review-bar"><div><ClipboardCheck size={18} /><span><strong>人工复核 <StatusBadge value={reviewStatus} /></strong><small>{reviewStatus === 'pending' ? '复核只更新诊断状态，不改写原始问题、标签或本次回答' : reviewStatus === 'confirmed' ? `故障归因已${apiMode === 'mock' ? '在当前页面' : '通过 API'}确认` : `该诊断已${apiMode === 'mock' ? '在当前页面' : '通过 API'}排除`}</small></span></div><div><button className="button button-secondary" type="button" aria-pressed={reviewStatus === 'dismissed'} disabled={savingReview || reviewStatus === 'dismissed'} onClick={() => void updateReview('dismissed')}><X size={15} />排除诊断</button><button className="button button-primary" type="button" aria-pressed={reviewStatus === 'confirmed'} disabled={savingReview || reviewStatus === 'confirmed'} onClick={() => void updateReview('confirmed')}><Check size={15} />确认故障归因</button></div></div>
      <Dialog open={sourceOpen && Boolean(selectedContext)} title={selectedContext?.title ?? selectedContext?.docId ?? '上下文详情'} eyebrow="CONTEXT SOURCE" onClose={() => setSourceOpen(false)}>
        {selectedContext && <><dl className="detail-list"><div><dt>上下文来源</dt><dd>{originLabel(selectedContext.origin)}</dd></div><div><dt>来源标识</dt><dd><code>{selectedContext.source ?? '未知'}</code></dd></div><div><dt>文档 / Chunk</dt><dd><code>{selectedContext.docId ?? '未知'}</code> / <code>{selectedContext.chunkId ?? '未知'}</code></dd></div><div><dt>检索运行 ID</dt><dd><code>{selectedContext.retrievalRunId ?? '无'}</code></dd></div><div><dt>排名 / 分数</dt><dd>#{selectedContext.rank ?? '未知'} · {selectedContext.score === null ? '分数未知' : selectedContext.score.toFixed(2)}</dd></div><div><dt>相关性 / 有用性</dt><dd>{selectedContext.relevanceGrade ?? '未知'} / {selectedContext.usefulness === null ? '未知' : selectedContext.usefulness ? '是' : '否'}</dd></div></dl><blockquote className="source-preview">{selectedContext.text || '片段内容未知'}</blockquote><p className="form-hint">这里只展示报告中已有的上下文元数据，不会打开内部地址或向任何模型、检索服务发送请求。</p></>}
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}
