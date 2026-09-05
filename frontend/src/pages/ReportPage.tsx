import { ArrowLeft, ArrowRight, CheckCircle2, Download, GitCompareArrows, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { apiClient, apiMode } from '../api/client';
import { FailureChart } from '../components/FailureChart';
import { Dialog, Toast } from '../components/Interaction';
import { MetricCard } from '../components/MetricCard';
import { Panel } from '../components/Panel';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner } from '../components/PageState';
import { SampleStack } from '../components/SampleStack';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { downloadTextFile } from '../lib/browser';
import { formatDateTime, formatScore } from '../lib/format';
import type { EvaluationReport, SampleSummary } from '../types';

type SampleFilter = 'all' | 'pending' | 'confirmed';

const emptyReport = (taskId: string): EvaluationReport => ({
  id: `empty-${taskId}`,
  schemaVersion: '2.0',
  task: {
    id: taskId,
    name: '空评测报告',
    datasetId: '',
    datasetName: '',
    status: 'completed',
    outcome: null,
    qualityStatus: 'not_evaluated',
    qualityVerdict: 'unknown',
    qualityScore: null,
    progress: 100,
    createdAt: new Date(0).toISOString(),
    completedAt: null,
    modelVersion: null,
    promptVersion: null,
    adapterId: null,
    providerId: null,
    isMock: null,
    totalSamples: 0,
    succeededSamples: 0,
    failedSamples: 0,
    schemaVersion: '2.0',
    executionSnapshot: null,
  },
  verdict: 'undetermined',
  verdictReason: '没有执行质量评估。',
  executionSummary: { outcome: null, totalCount: 0, succeededCount: 0, failedCount: 0, successRate: null },
  qualitySummary: { status: 'not_evaluated', verdict: 'unknown', score: null, evaluatedSampleCount: 0 },
  executionSnapshot: null,
  isSimulated: null,
  metrics: [],
  failures: [],
  samples: [],
  generatedAt: null,
  baselineLabel: null,
});

const executionLabel = (outcome: EvaluationReport['executionSummary']['outcome']) => outcome === 'succeeded'
  ? '执行成功'
  : outcome === 'partial_failed' ? '部分执行失败' : outcome === 'failed' ? '执行失败' : '尚无结果';

function sampleMarkdown(sample: SampleSummary): string {
  const contexts = sample.contexts.length === 0
    ? '- 上下文：无记录'
    : sample.contexts.map((context) => `  - #${context.rank ?? '未知'} ${context.origin} · doc=${context.docId ?? '未知'} · chunk=${context.chunkId ?? '未知'} · score=${context.score ?? '未知'}\n    - ${context.text || '内容未知'}`).join('\n');
  const citations = sample.citations.length === 0
    ? '- 引用：无记录'
    : sample.citations.map((citation) => `  - ${citation.marker} · resolved=${citation.resolved ?? '未知'} · supports_claim=${citation.supportsClaim ?? '未评估'} · target=${citation.targetId || '未知'}`).join('\n');
  return `#### ${sample.sampleId}\n\n- 原始问题：${sample.question}\n- 参考答案：${sample.referenceAnswer ?? '未知'}\n- 本次回答：${sample.generatedAnswer ?? '未知'}\n- 历史回答：${sample.historicalAnswer ?? '无记录'}\n- 运行状态：${sample.runStatus}\n- 质量状态：${sample.qualityStatus}\n- 延迟：${sample.latencyMs === null ? '未知' : `${sample.latencyMs}ms`}\n- 错误：${sample.error ? `${sample.error.code} · ${sample.error.message}` : '无'}\n\n${contexts}\n\n${citations}`;
}

export function ReportPage() {
  const { projectId = 'demo', taskId = '' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const [sampleFilter, setSampleFilter] = useState<SampleFilter>('all');
  const [sampleView, setSampleView] = useState<'stack' | 'table'>('stack');
  const [compareOpen, setCompareOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const { state, retry } = useApiResource(
    () => apiClient.getEvaluationReport(projectId, taskId),
    [projectId, taskId],
    {
      scenario,
      emptyValue: emptyReport(taskId),
      partialize: (data) => ({
        ...data,
        verdict: 'undetermined' as const,
        verdictReason: '部分质量字段缺失，当前无法给出质量门结论。',
        qualitySummary: { ...data.qualitySummary, status: 'partial' as const, verdict: 'unknown' as const, score: null },
        metrics: data.metrics.map((metric, index) => index === 2 ? { ...metric, value: null, status: 'not_evaluated' as const } : metric),
        warnings: [...(data.warnings ?? []), '部分指标仍在计算。'],
      }),
    },
  );

  if (state.status === 'loading') return <LoadingState label="正在读取评测报告" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  const report = state.data;
  const snapshot = report.executionSnapshot;
  const filteredSamples = sampleFilter === 'all'
    ? report.samples
    : report.samples.filter((sample) => sample.reviewStatus === sampleFilter);

  const exportReport = async (format: 'json' | 'markdown') => {
    setExporting(true);
    try {
      const artifact = await apiClient.exportEvaluationReport(projectId, taskId);
      const exportableReport = artifact.report;
      if (format === 'json') {
        downloadTextFile(`${exportableReport.task.id}-report.json`, JSON.stringify(artifact.artifact, null, 2), 'application/json;charset=utf-8');
      } else {
        const metricLines = exportableReport.metrics.map((metric) => `| ${metric.label} | ${metric.status} | ${metric.value ?? '未知'} |`).join('\n');
        const sampleLines = exportableReport.samples.map(sampleMarkdown).join('\n\n');
        const markdown = `## ${exportableReport.task.name}\n\n- Schema：${exportableReport.schemaVersion}\n- 任务：${exportableReport.task.id}\n- 生命周期：${exportableReport.task.status}\n- 执行结果：${exportableReport.executionSummary.outcome ?? '未知'}\n- 质量状态：${exportableReport.qualitySummary.status}\n- 质量结论：${exportableReport.qualitySummary.verdict}\n- 质量分：${exportableReport.qualitySummary.score ?? '未知'}\n- 执行器：${exportableReport.task.adapterId ?? '未知'}\n- 模型：${exportableReport.task.modelVersion ?? '未知'}\n- Prompt：${exportableReport.task.promptVersion ?? '未知'}\n- 模拟结果：${exportableReport.isSimulated === null ? '未知' : exportableReport.isSimulated ? '是' : '否'}\n- 生成时间：${exportableReport.generatedAt ?? '未知'}\n\n${exportableReport.verdictReason}\n\n### 指标\n\n| 指标 | 状态 | 值 |\n| --- | --- | ---: |\n${metricLines}\n\n### 样本运行与证据\n\n${sampleLines || '无样本记录'}\n`;
        downloadTextFile(`${exportableReport.task.id}-report.md`, markdown, 'text/markdown;charset=utf-8');
      }
      setExportOpen(false);
      setFeedback(`已导出 ${format === 'json' ? 'JSON' : 'Markdown'} 报告${report.isSimulated ? '（含 SIMULATED 标识）' : ''}`);
    } catch (error) {
      setFeedback(error instanceof Error ? `导出失败：${error.message}` : '导出失败，请稍后重试');
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <BackLink projectId={projectId} />
      <div className="report-heading">
        <div>
          <span className="eyebrow">{report.task.id} · SCHEMA {report.schemaVersion}</span>
          <h2>{report.task.name} {report.isSimulated === true && <em className="mock-label" aria-hidden="true">SIMULATED REPORT</em>}</h2>
          <p>{report.task.datasetName || '数据集未知'} · {report.task.modelVersion ?? '模型未知'} · {report.task.promptVersion ?? 'Prompt 未知'}</p>
        </div>
        <div className="page-actions"><button className="button button-secondary" type="button" onClick={() => setCompareOpen(true)}><GitCompareArrows size={15} />对比版本</button><button className="button button-secondary" type="button" onClick={() => setExportOpen(true)}><Download size={15} />导出报告</button></div>
      </div>
      <PartialDataBanner message={state.partialMessage} />
      {report.warnings?.map((warning) => <PartialDataBanner key={warning} message={warning} />)}
      <div className="summary-strip report-status-strip" aria-label="运行与质量状态">
        <div><span>任务生命周期</span><strong><StatusBadge value={report.task.status} /></strong></div>
        <div><span>执行结果</span><strong>{report.executionSummary.outcome ? <StatusBadge value={report.executionSummary.outcome} /> : '尚无结果'}</strong></div>
        <div><span>质量状态</span><strong><StatusBadge value={report.qualitySummary.status} /></strong></div>
        <div><span>质量分</span><strong>{report.qualitySummary.score ?? '未知'}</strong></div>
      </div>
      <section className={`verdict-card verdict-${report.verdict}`}>
        <div className="verdict-icon">{report.verdict === 'passed' ? <CheckCircle2 size={25} /> : <ShieldAlert size={25} />}</div>
        <div><span>质量门结论</span><h3>{report.verdict === 'passed' ? '通过' : report.verdict === 'failed' ? '不通过' : '未知'}</h3><p>{report.verdictReason}</p></div>
        <div className="verdict-meta"><span>执行汇总</span><strong>{executionLabel(report.executionSummary.outcome)}</strong><small>{report.executionSummary.succeededCount} 成功 / {report.executionSummary.failedCount} 失败 · {report.generatedAt ? `生成于 ${formatDateTime(report.generatedAt)}` : '生成时间未知'}</small></div>
      </section>
      <div className="metric-grid">{report.metrics.map((metric) => <MetricCard key={metric.key} metric={metric} />)}</div>
      <div className="dashboard-grid report-grid">
        <Panel title="诊断类型分布" eyebrow={`${report.failures.reduce((sum, item) => sum + item.count, 0)} 条诊断`}><FailureChart buckets={report.failures} /></Panel>
        <Panel title="运行快照" eyebrow="REPRODUCIBILITY">
          <dl className="config-list">
            <div><dt>执行器 / 提供方</dt><dd><code>{snapshot?.adapterId ?? report.task.adapterId ?? '未知'}</code> / <code>{snapshot?.providerId ?? report.task.providerId ?? '无或未知'}</code></dd></div>
            <div><dt>请求模型</dt><dd><code>{snapshot?.generation.model ?? report.task.modelVersion ?? '未知'}</code></dd></div>
            <div><dt>Prompt 版本</dt><dd><code>{snapshot?.prompt.version ?? report.task.promptVersion ?? '未知'}</code></dd></div>
            <div><dt>数据集版本</dt><dd>{snapshot ? `${snapshot.dataset.id} · ${snapshot.dataset.version} · schema ${snapshot.dataset.schemaVersion}` : '旧记录 / 未知'}</dd></div>
            <div><dt>上下文策略</dt><dd>{snapshot?.contextPolicy ?? '未知'}</dd></div>
            <div><dt>创建时网络开关</dt><dd>{snapshot ? snapshot.externalCallsEnabledAtCreation ? '已开启' : '已关闭' : '未知'}</dd></div>
            <div><dt>配置版本</dt><dd><code>{snapshot?.configVersion ?? '未知'}</code></dd></div>
          </dl>
        </Panel>
      </div>
      <section className="sample-browser" aria-labelledby="sample-browser-title">
        <header className="section-heading"><div><h2 id="sample-browser-title">样本运行记录</h2><p>问题、标签、本次输出与证据。</p></div><div className="segmented" aria-label="样本展示方式"><button type="button" aria-pressed={sampleView === 'stack'} onClick={() => setSampleView('stack')}>卡片浏览</button><button type="button" aria-pressed={sampleView === 'table'} onClick={() => setSampleView('table')}>表格列表</button></div></header>
        <div className="segmented sample-filters" aria-label="复核状态筛选"><button aria-pressed={sampleFilter === 'all'} type="button" onClick={() => setSampleFilter('all')}>全部 {report.samples.length}</button><button aria-pressed={sampleFilter === 'pending'} type="button" onClick={() => setSampleFilter('pending')}>待复核 {report.samples.filter((sample) => sample.reviewStatus === 'pending').length}</button><button aria-pressed={sampleFilter === 'confirmed'} type="button" onClick={() => setSampleFilter('confirmed')}>已确认 {report.samples.filter((sample) => sample.reviewStatus === 'confirmed').length}</button></div>
        {filteredSamples.length === 0 ? <EmptyState title="没有可展示的样本记录" description="终态报告仍然可查看执行与质量汇总；当前没有符合筛选条件的样本。" /> : sampleView === 'stack' ? <SampleStack samples={filteredSamples} projectId={projectId} taskId={taskId} /> : <div className="table-wrap">
          <table>
            <thead><tr><th>原始问题</th><th>运行</th><th>质量</th><th>Recall@5</th><th>忠实性</th><th>引用支持</th><th>延迟 / 错误</th><th>复核</th><th /></tr></thead>
            <tbody>{filteredSamples.map((sample) => (
              <tr key={sample.id}>
                <td className="question-cell"><strong>{sample.question}</strong><small>{sample.sampleId} · 参考：{sample.referenceAnswer ?? '未知'}</small></td>
                <td><StatusBadge value={sample.runStatus} />{sample.isMock === true && <small>SIMULATED</small>}</td>
                <td><StatusBadge value={sample.qualityStatus} /></td>
                <td>{formatScore(sample.recallAt5, sample.recallAt5Status)}</td>
                <td>{formatScore(sample.faithfulness, sample.faithfulnessStatus)}</td>
                <td>{formatScore(sample.citationSupportRate, sample.citationSupportStatus)}</td>
                <td>{sample.latencyMs === null ? '未知' : `${sample.latencyMs}ms`}{sample.error && <small className="text-critical">{sample.error.code} · {sample.error.message}</small>}</td>
                <td><StatusBadge value={sample.reviewStatus} /></td>
                <td><Link aria-label={`诊断样本 ${sample.id}`} className="button button-small" to={`/projects/${projectId}/evaluations/${taskId}/samples/${sample.id}`}>诊断 <ArrowRight size={14} /></Link></td>
              </tr>
            ))}</tbody>
          </table>
        </div>}
      </section>

      <Dialog open={compareOpen} title="版本对比" eyebrow="CURRENT VS BASELINE" onClose={() => setCompareOpen(false)}>
        <div className="compare-summary"><div><span>当前版本</span><strong>{report.task.modelVersion ?? '模型未知'}</strong><code>{report.task.promptVersion ?? 'Prompt 未知'}</code></div><GitCompareArrows size={22} /><div><span>对比基线</span><strong>{report.baselineLabel ?? '未提供'}</strong><small>不从当前值反推基线</small></div></div>
        <p className="form-hint">报告没有明确基线值时不生成估算变化；版本对比需要服务端返回可追溯的独立基线记录。</p>
      </Dialog>
      <Dialog open={exportOpen} title="导出评测报告" eyebrow="PORTABLE ARTIFACT" onClose={() => setExportOpen(false)}>
        <p>JSON 保留后端完整 2.0 报告与样本结构；Markdown 同时列出原始问题、参考答案、本次回答、上下文来源、引用和运行错误。</p>
        <div className="export-options"><button type="button" disabled={exporting} onClick={() => void exportReport('json')}><strong>JSON</strong><span>{apiMode === 'mock' ? '明确标记 SIMULATED 的 fixture 导出' : '服务端原始完整导出'}</span></button><button type="button" disabled={exporting} onClick={() => void exportReport('markdown')}><strong>Markdown</strong><span>适合审计的可读证据摘要</span></button></div>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}

function BackLink({ projectId }: { projectId: string }) {
  return <Link className="back-link" to={`/projects/${projectId}/evaluations`}><ArrowLeft size={15} />返回评测任务</Link>;
}
