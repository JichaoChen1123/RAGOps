import { ArrowLeft, ArrowRight, CheckCircle2, Download, GitCompareArrows, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import { FailureChart } from '../components/FailureChart';
import { Dialog, Toast } from '../components/Interaction';
import { MetricCard } from '../components/MetricCard';
import { Panel } from '../components/Panel';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { downloadTextFile } from '../lib/browser';
import { formatDateTime, formatScore } from '../lib/format';
import type { EvaluationReport } from '../types';

type SampleFilter = 'all' | 'pending' | 'confirmed';

const emptyReport = (taskId: string): EvaluationReport => ({
  id: `empty-${taskId}`,
  task: {
    id: taskId, name: '空评测报告', datasetId: '', datasetName: '', status: 'completed', progress: 100,
    createdAt: new Date(0).toISOString(), modelVersion: '', promptVersion: '', totalSamples: 0,
  },
  verdict: 'undetermined', verdictReason: '没有可用于生成报告的样本。', metrics: [], failures: [], samples: [],
  generatedAt: new Date(0).toISOString(), baselineLabel: '',
});

export function ReportPage() {
  const { projectId = 'demo', taskId = '' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const [sampleFilter, setSampleFilter] = useState<SampleFilter>('all');
  const [compareOpen, setCompareOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const { state, retry } = useApiResource(
    () => apiClient.getEvaluationReport(projectId, taskId),
    [projectId, taskId],
    {
      scenario,
      emptyValue: emptyReport(taskId),
      partialize: (data) => ({
        ...data,
        verdict: 'undetermined' as const,
        verdictReason: '答案质量指标尚未完成聚合，当前无法给出门禁结论。',
        metrics: data.metrics.map((metric, index) => index === 2 ? { ...metric, value: null } : metric),
        warnings: ['答案忠实性仍在计算。'],
      }),
    },
  );

  if (state.status === 'loading') return <LoadingState label="正在生成评测报告视图" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  const report = state.data;
  const filteredSamples = sampleFilter === 'all'
    ? report.samples
    : report.samples.filter((sample) => sample.reviewStatus === sampleFilter);

  if (report.samples.length === 0) {
    return <><BackLink projectId={projectId} /><EmptyState title="报告没有可用样本" description="任务已完成，但当前筛选条件下没有可展示的指标或样本。" /></>;
  }

  const exportReport = (format: 'json' | 'markdown') => {
    if (format === 'json') {
      downloadTextFile(`${report.task.id}-report.json`, JSON.stringify(report, null, 2), 'application/json;charset=utf-8');
    } else {
      const metricLines = report.metrics.map((metric) => `| ${metric.label} | ${metric.value ?? '不可计算'}${metric.unit ?? ''} | ${metric.threshold ?? '—'}${metric.unit ?? ''} |`).join('\n');
      const sampleLines = report.samples.map((sample) => `- ${sample.id} · ${sample.failureType} · ${sample.reviewStatus}: ${sample.question}`).join('\n');
      const markdown = `## ${report.task.name}\n\n- 任务：${report.task.id}\n- 门禁：${report.verdict}\n- 数据集：${report.task.datasetName}\n- 模型 / Prompt：${report.task.modelVersion} / ${report.task.promptVersion}\n- 生成时间：${report.generatedAt}\n\n${report.verdictReason}\n\n### 指标\n\n| 指标 | 当前值 | 门槛 |\n| --- | ---: | ---: |\n${metricLines}\n\n### 失败样本\n\n${sampleLines}\n`;
      downloadTextFile(`${report.task.id}-report.md`, markdown, 'text/markdown;charset=utf-8');
    }
    setExportOpen(false);
    setFeedback(`已导出 ${format === 'json' ? 'JSON' : 'Markdown'} 报告`);
  };

  return (
    <>
      <BackLink projectId={projectId} />
      <div className="report-heading">
        <div>
          <span className="eyebrow">{report.task.id}</span>
          <h2>{report.task.name}</h2>
          <p>{report.task.datasetName} · {report.task.modelVersion} · {report.task.promptVersion}</p>
        </div>
        <div className="page-actions"><button className="button button-secondary" type="button" onClick={() => setCompareOpen(true)}><GitCompareArrows size={15} />对比版本</button><button className="button button-secondary" type="button" onClick={() => setExportOpen(true)}><Download size={15} />导出报告</button></div>
      </div>
      <PartialDataBanner message={state.partialMessage} />
      <section className={`verdict-card verdict-${report.verdict}`}>
        <div className="verdict-icon">{report.verdict === 'passed' ? <CheckCircle2 size={25} /> : <ShieldAlert size={25} />}</div>
        <div><span>发布门禁结论</span><h3>{report.verdict === 'passed' ? '通过' : report.verdict === 'failed' ? '不通过' : '无法判断'}</h3><p>{report.verdictReason}</p></div>
        <div className="verdict-meta"><span>基线</span><strong>{report.baselineLabel}</strong><small>生成于 {formatDateTime(report.generatedAt)}</small></div>
      </section>
      <div className="metric-grid">{report.metrics.map((metric) => <MetricCard key={metric.key} metric={metric} />)}</div>
      <div className="dashboard-grid report-grid">
        <Panel title="失败类型分布" eyebrow={`${report.task.failedSamples ?? 0} / ${report.task.totalSamples} 条`}><FailureChart buckets={report.failures} /></Panel>
        <Panel title="运行配置" eyebrow="REPRODUCIBILITY">
          <dl className="config-list"><div><dt>数据集</dt><dd>{report.task.datasetName}</dd></div><div><dt>模型版本</dt><dd><code>{report.task.modelVersion}</code></dd></div><div><dt>Prompt 版本</dt><dd><code>{report.task.promptVersion}</code></dd></div><div><dt>完成时间</dt><dd>{formatDateTime(report.task.completedAt)}</dd></div></dl>
        </Panel>
      </div>
      <Panel title="失败样本" eyebrow="按严重程度排序" action={<div className="segmented"><button className={sampleFilter === 'all' ? 'active' : ''} type="button" onClick={() => setSampleFilter('all')}>全部 {report.samples.length}</button><button className={sampleFilter === 'pending' ? 'active' : ''} type="button" onClick={() => setSampleFilter('pending')}>待复核 {report.samples.filter((sample) => sample.reviewStatus === 'pending').length}</button><button className={sampleFilter === 'confirmed' ? 'active' : ''} type="button" onClick={() => setSampleFilter('confirmed')}>已确认 {report.samples.filter((sample) => sample.reviewStatus === 'confirmed').length}</button></div>}>
        {filteredSamples.length === 0 ? <EmptyState title="该分段没有样本" description="切换到其他复核状态查看失败样本。" /> : <div className="table-wrap">
          <table>
            <thead><tr><th>问题</th><th>疑似原因</th><th>Recall@5</th><th>忠实性</th><th>引用命中</th><th>延迟</th><th>复核</th><th /></tr></thead>
            <tbody>{filteredSamples.map((sample) => (
              <tr key={sample.id}>
                <td className="question-cell"><strong>{sample.question}</strong><small>{sample.id}</small></td>
                <td><StatusBadge value={sample.severity} /> <span>{sample.failureType}</span></td>
                <td>{formatScore(sample.recallAt5)}</td><td>{formatScore(sample.faithfulness)}</td><td>{formatScore(sample.citationHitRate)}</td><td>{sample.latencyMs}ms</td>
                <td><StatusBadge value={sample.reviewStatus} /></td>
                <td><Link aria-label={`诊断样本 ${sample.id}`} className="button button-small" to={`/projects/${projectId}/evaluations/${taskId}/samples/${sample.id}`}>诊断 <ArrowRight size={14} /></Link></td>
              </tr>
            ))}</tbody>
          </table>
        </div>}
      </Panel>

      <Dialog open={compareOpen} title="版本对比" eyebrow="CURRENT VS BASELINE" onClose={() => setCompareOpen(false)}>
        <div className="compare-summary"><div><span>当前版本</span><strong>{report.task.modelVersion}</strong><code>{report.task.promptVersion}</code></div><GitCompareArrows size={22} /><div><span>对比基线</span><strong>{report.baselineLabel}</strong><small>来自当前报告基线</small></div></div>
        <div className="table-wrap compact-table"><table><thead><tr><th>指标</th><th>基线估值</th><th>当前值</th><th>变化</th></tr></thead><tbody>{report.metrics.map((metric) => { const baseline = metric.value !== null && metric.delta !== null && metric.delta !== undefined ? metric.value - metric.delta : null; return <tr key={metric.key}><td>{metric.label}</td><td>{baseline === null ? '—' : `${baseline.toFixed(1)}${metric.unit ?? ''}`}</td><td>{metric.value === null ? '—' : `${metric.value}${metric.unit ?? ''}`}</td><td className={(metric.delta ?? 0) >= 0 ? 'text-positive' : 'text-critical'}>{metric.delta === null || metric.delta === undefined ? '—' : `${metric.delta > 0 ? '+' : ''}${metric.delta}${metric.unit ?? ''}`}</td></tr>; })}</tbody></table></div>
        <p className="form-hint">MVP 对比使用报告中的基线标签与指标变化值推导，不会把推导结果写回服务端。</p>
      </Dialog>
      <Dialog open={exportOpen} title="导出评测报告" eyebrow="PORTABLE ARTIFACT" onClose={() => setExportOpen(false)}>
        <p>选择适合后续审计或协作的格式。导出内容来自当前已载入的报告数据。</p>
        <div className="export-options"><button type="button" onClick={() => exportReport('json')}><strong>JSON</strong><span>完整字段，适合程序处理与归档</span></button><button type="button" onClick={() => exportReport('markdown')}><strong>Markdown</strong><span>指标与失败样本摘要，适合评审</span></button></div>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}

function BackLink({ projectId }: { projectId: string }) {
  return <Link className="back-link" to={`/projects/${projectId}/evaluations`}><ArrowLeft size={15} />返回评测任务</Link>;
}
