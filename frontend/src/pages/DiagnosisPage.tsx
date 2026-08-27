import { ArrowLeft, Check, ChevronRight, ClipboardCheck, Copy, ExternalLink, SearchX, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import { Dialog, Toast } from '../components/Interaction';
import { MetricCard } from '../components/MetricCard';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { copyText } from '../lib/browser';
import { formatDateTime } from '../lib/format';
import type { SampleDiagnosis } from '../types';

const emptyDiagnosis = (taskId: string, sampleId: string): SampleDiagnosis => ({
  id: sampleId, taskId, question: '', expectedAnswer: '', generatedAnswer: '', metrics: [],
  primaryDiagnosis: { label: '不可判定', confidence: null, severity: 'unknown', explanation: '样本缺少诊断输入。', evidenceIds: [] },
  secondaryDiagnoses: [], retrievedDocuments: [], citations: [], traceId: '', evaluatedAt: new Date(0).toISOString(),
});

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
        metrics: data.metrics.map((metric, index) => index > 1 ? { ...metric, value: null } : metric),
        citations: data.citations.slice(0, 1),
        warnings: ['引用对齐结果仅返回 1 / 2 条。'],
      }),
    },
  );
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [reviewStatus, setReviewStatus] = useState<'pending' | 'confirmed' | 'dismissed'>('pending');
  const [feedback, setFeedback] = useState<string | null>(null);

  const selectedDocument = useMemo(() => state.status === 'success'
    ? state.data.retrievedDocuments.find((document) => document.id === selectedDocumentId) ?? state.data.retrievedDocuments[0]
    : undefined, [selectedDocumentId, state]);

  if (state.status === 'loading') return <LoadingState label="正在还原样本证据链" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  const diagnosis = state.data;

  if (!diagnosis.question) {
    return <><Link className="back-link" to={`/projects/${projectId}/evaluations/${taskId}/report`}><ArrowLeft size={15} />返回评测报告</Link><EmptyState title="样本没有诊断数据" description="当前样本缺少问题、检索结果或模型回答，无法进行故障归因。" /></>;
  }

  const selectCitation = (documentId: string) => {
    setSelectedDocumentId(documentId);
    document.getElementById('evidence-detail')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };

  const copyAnswer = async () => {
    try {
      await copyText(diagnosis.generatedAnswer);
      setFeedback('已复制模型回答');
    } catch {
      setFeedback('复制失败，请手动选择模型回答');
    }
  };

  const updateReview = (next: 'confirmed' | 'dismissed') => {
    setReviewStatus(next);
    setFeedback(next === 'confirmed' ? '已确认故障归因（仅当前页面会话）' : '已排除本次诊断（仅当前页面会话）');
  };

  return (
    <>
      <div className="diagnosis-nav">
        <Link className="back-link" to={`/projects/${projectId}/evaluations/${taskId}/report`}><ArrowLeft size={15} />返回评测报告</Link>
        <span>样本 {diagnosis.id} · {formatDateTime(diagnosis.evaluatedAt)} · <code>{diagnosis.traceId}</code></span>
      </div>
      <PartialDataBanner message={state.partialMessage} />
      <section className="question-card">
        <span className="eyebrow">QUESTION</span><h2>{diagnosis.question}</h2>
        <div className="diagnosis-metrics">{diagnosis.metrics.map((metric) => <MetricCard compact key={metric.key} metric={metric} />)}</div>
      </section>
      <section className="diagnosis-callout">
        <div className="diagnosis-symbol"><SearchX size={21} /></div>
        <div><span>主要疑似原因</span><h3>{diagnosis.primaryDiagnosis.label}</h3><p>{diagnosis.primaryDiagnosis.explanation}</p></div>
        <div className="confidence"><small>置信度</small><strong>{diagnosis.primaryDiagnosis.confidence === null ? '不可判定' : `${Math.round(diagnosis.primaryDiagnosis.confidence * 100)}%`}</strong><StatusBadge value={diagnosis.primaryDiagnosis.severity} /></div>
      </section>
      <div className="evidence-layout">
        <section className="evidence-column">
          <header><span>01</span><div><strong>检索结果</strong><small>点击文档查看证据片段</small></div></header>
          <div className="document-list">
            {diagnosis.retrievedDocuments.map((document) => (
              <button className={`document-item ${selectedDocument?.id === document.id ? 'selected' : ''} ${document.isExpected ? 'expected' : ''}`} type="button" key={document.id} onClick={() => setSelectedDocumentId(document.id)}>
                <span className="rank">#{document.rank}</span><span className="document-copy"><strong>{document.title}</strong><small>{document.source}</small><em>{document.snippet}</em></span>
                <span className="document-score"><strong>{document.score.toFixed(2)}</strong><small>向量分</small>{document.isExpected && <i>期望文档</i>}</span>
              </button>
            ))}
          </div>
        </section>
        <section className="answer-column">
          <header><span>02</span><div><strong>回答与引用</strong><small>逐条核对声明与来源</small></div></header>
          <div className="answer-block expected-answer"><span>期望答案</span><p>{diagnosis.expectedAnswer}</p></div>
          <div className="answer-block generated-answer">
            <span>模型回答 <button type="button" aria-label="复制模型回答" onClick={() => void copyAnswer()}><Copy size={13} /></button></span><p>{diagnosis.generatedAnswer}</p>
            <div className="citation-list">{diagnosis.citations.map((citation) => <button key={citation.id} className="citation-chip" type="button" onClick={() => selectCitation(citation.documentId)}>{citation.marker} {citation.supported ? <Check size={13} /> : <X size={13} />} {citation.supported ? '支持' : '不支持'} <ChevronRight size={13} /></button>)}</div>
          </div>
          {diagnosis.secondaryDiagnoses.map((item) => <div className="secondary-diagnosis" key={item.label}><StatusBadge value={item.severity} /><div><strong>{item.label}</strong><p>{item.explanation}</p></div></div>)}
        </section>
      </div>
      {selectedDocument && (
        <section className="evidence-detail" id="evidence-detail">
          <header><div><span className="eyebrow">EVIDENCE DETAIL</span><h3>{selectedDocument.title}</h3></div><button className="button button-secondary" type="button" onClick={() => setSourceOpen(true)}><ExternalLink size={14} />打开源文档</button></header>
          <div className="evidence-meta"><span>Rank <strong>#{selectedDocument.rank}</strong></span><span>Chunk <code>{selectedDocument.chunkId}</code></span><span>Score <strong>{selectedDocument.score.toFixed(2)}</strong></span><span>期望证据 <strong>{selectedDocument.isExpected ? '是' : '否'}</strong></span></div>
          <blockquote>{selectedDocument.snippet}</blockquote>
        </section>
      )}
      <div className="review-bar"><div><ClipboardCheck size={18} /><span><strong>人工复核 <StatusBadge value={reviewStatus} /></strong><small>{reviewStatus === 'pending' ? '确认诊断后可进入回归样本池' : reviewStatus === 'confirmed' ? '故障归因已在当前页面确认' : '该诊断已在当前页面排除'}</small></span></div><div><button className="button button-secondary" type="button" aria-pressed={reviewStatus === 'dismissed'} disabled={reviewStatus === 'dismissed'} onClick={() => updateReview('dismissed')}><X size={15} />排除诊断</button><button className="button button-primary" type="button" aria-pressed={reviewStatus === 'confirmed'} disabled={reviewStatus === 'confirmed'} onClick={() => updateReview('confirmed')}><Check size={15} />确认故障归因</button></div></div>
      <Dialog open={sourceOpen && Boolean(selectedDocument)} title={selectedDocument?.title ?? '源文档'} eyebrow="SOURCE DOCUMENT" onClose={() => setSourceOpen(false)}>
        {selectedDocument && <><dl className="detail-list"><div><dt>来源</dt><dd><code>{selectedDocument.source}</code></dd></div><div><dt>Chunk</dt><dd><code>{selectedDocument.chunkId}</code></dd></div><div><dt>检索排名 / 分数</dt><dd>#{selectedDocument.rank} · {selectedDocument.score.toFixed(2)}</dd></div><div><dt>期望证据</dt><dd>{selectedDocument.isExpected ? '是' : '否'}</dd></div></dl><blockquote className="source-preview">{selectedDocument.snippet}</blockquote><p className="form-hint">Mock 模式展示已返回的来源元数据与片段，不会尝试打开 <code>kb://</code> 内部地址。</p></>}
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}
