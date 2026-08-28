import {
  ArrowRight,
  BadgeCheck,
  Bot,
  CalendarRange,
  Database,
  FileCheck2,
  GitBranch,
  Microscope,
  Play,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { apiClient, apiMode } from '../api/client';
import { FailureChart } from '../components/FailureChart';
import { Dialog, Toast } from '../components/Interaction';
import { MetricCard } from '../components/MetricCard';
import { PageIntro, Panel } from '../components/Panel';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import { TrendChart } from '../components/TrendChart';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { formatDateTime } from '../lib/format';
import type { ProjectOverview } from '../types';

const emptyOverview: ProjectOverview = {
  project: { id: 'demo', name: '客服 RAG 生产线', description: '', environment: 'production-shadow', updatedAt: new Date(0).toISOString() },
  metrics: [], recentTasks: [], failureDistribution: [], trend: [],
};

const pipelineSteps = [
  { label: 'Dataset', title: '数据集', detail: 'v3.4 · 120 samples', state: 'READY', icon: Database },
  { label: 'Evaluation Job', title: '评测任务', detail: 'eval-20260826', state: 'DONE', icon: Play },
  { label: 'Metrics', title: '指标计算', detail: '5 metrics · gate-aware', state: 'PASS', icon: Microscope },
  { label: 'Failure Diagnosis', title: '失败诊断', detail: '4 rules · evidence-linked', state: 'TRACE', icon: ScanSearch },
  { label: 'Report', title: '评测报告', detail: 'JSON · audit ready', state: 'READY', icon: FileCheck2 },
  { label: 'Review', title: '人工复核', detail: '1 pending · feedback loop', state: 'OPEN', icon: BadgeCheck },
];

const capabilityGroups = [
  {
    label: 'METRICS',
    title: '多维质量评测',
    icon: Microscope,
    status: '已接入',
    items: ['Recall@5', 'Faithfulness', 'Citation hit', 'P95 latency'],
  },
  {
    label: 'DIAGNOSIS RULES',
    title: '证据级故障归因',
    icon: ScanSearch,
    status: '4 条规则',
    items: ['检索缺失', '上下文污染', '引用冲突', 'Prompt 约束弱'],
  },
  {
    label: 'VERSION TRACE',
    title: '运行版本可追溯',
    icon: GitBranch,
    status: '已固定',
    items: ['Dataset v3.4', 'qwen3-32b', 'Prompt v12', 'Evaluation config'],
  },
  {
    label: 'DELIVERY GATE',
    title: '工程质量门禁',
    icon: ShieldCheck,
    status: 'PASS',
    items: ['TypeScript', 'Vitest', 'Build', 'Score ≥ 80'],
  },
];

function RuntimeContext() {
  return (
    <section className="runtime-context" aria-label="当前评测运行上下文">
      <div><span className={`runtime-signal runtime-${apiMode}`}><i />{apiMode === 'mock' ? 'MOCK FIXTURE' : 'LIVE API'}</span><small>数据模式</small></div>
      <div><Bot size={15} /><span><strong>qwen3-32b@2026-08</strong><small>Model version</small></span></div>
      <div><GitBranch size={15} /><span><strong>support-rag@v12</strong><small>Prompt version</small></span></div>
      <div><ShieldCheck size={15} /><span><strong>PASS · 82.4 ≥ 80</strong><small>Quality gate</small></span></div>
    </section>
  );
}

function TechnicalCapabilities() {
  return (
    <section className="technical-overview" aria-labelledby="ragops-pipeline-title">
      <header className="technical-heading">
        <div><span className="eyebrow">OBSERVABLE RAG EVALUATION</span><h2 id="ragops-pipeline-title">RAGOps 技术链路</h2><p>从评测数据到人工复核，每个结论都保留版本、指标、规则与证据上下文。</p></div>
        <span className="trace-status"><i /> TRACE ENABLED</span>
      </header>
      <ol className="pipeline" aria-label="Dataset 到 Review 的评测链路">
        {pipelineSteps.map((step) => {
          const StepIcon = step.icon;
          return (
            <li key={step.label}>
              <div className="pipeline-icon"><StepIcon size={16} /></div>
              <div><span>{step.label}</span><strong>{step.title}</strong><small>{step.detail}</small></div>
              <i>{step.state}</i>
            </li>
          );
        })}
      </ol>
      <div className="capability-header"><span>CAPABILITY MATRIX</span><strong>评测、诊断、版本与交付门禁</strong></div>
      <div className="capability-grid">
        {capabilityGroups.map((group) => {
          const GroupIcon = group.icon;
          return (
            <article key={group.label} className="capability-card">
              <header><span><GroupIcon size={15} /></span><div><small>{group.label}</small><strong>{group.title}</strong></div><i>{group.status}</i></header>
              <div>{group.items.map((item) => <code key={item}>{item}</code>)}</div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function OverviewPage() {
  const { projectId = 'demo' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const [trendOpen, setTrendOpen] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const { state, retry } = useApiResource(
    () => apiClient.getProjectOverview(projectId),
    [projectId],
    {
      scenario,
      emptyValue: emptyOverview,
      partialize: (data) => ({
        ...data,
        metrics: data.metrics.map((metric, index) => index > 2 ? { ...metric, value: null, delta: null } : metric),
        warnings: ['成本与尾延迟聚合仍在计算。'],
      }),
    },
  );

  if (state.status === 'loading') return <LoadingState label="正在载入项目健康度" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  const data = state.data;

  const refreshOverview = () => {
    setFeedback(apiMode === 'mock' ? '正在重新载入 Mock 项目数据' : '正在从 LIVE API 刷新项目数据');
    retry();
  };

  return (
    <>
      <PageIntro
        eyebrow="PRODUCTION SHADOW"
        title={data.project.name}
        description="追踪离线质量、失败样本与端到端性能；所有门禁结论均可下钻到证据。"
        actions={<><button className="button button-secondary" type="button" onClick={refreshOverview}><RefreshCw size={15} />刷新数据</button><Link className="button button-primary" to={`/projects/${projectId}/evaluations`}><Play size={15} />新建评测</Link></>}
      />
      <RuntimeContext />
      <PartialDataBanner message={state.partialMessage} />
      {data.metrics.length === 0 ? (
        <EmptyState title="尚无评测数据" description="创建首个数据集并运行评测后，这里将展示项目质量基线。" action={<Link className="button button-primary" to={`/projects/${projectId}/datasets`}>前往数据集</Link>} />
      ) : (
        <>
          <div className="metric-grid">{data.metrics.map((metric) => <MetricCard key={metric.key} metric={metric} />)}</div>
          <TechnicalCapabilities />
          <div className="dashboard-grid">
            <Panel title="质量趋势" eyebrow="最近 7 次评测" action={<button className="text-button" type="button" onClick={() => setTrendOpen(true)}>查看趋势看板 <ArrowRight size={14} /></button>} className="panel-wide">
              <span id="quality-trends" className="anchor-target" />
              <TrendChart points={data.trend} />
              <div className="chart-legend"><span><i className="legend-blue" />综合质量分</span><span><i className="legend-muted" />目标线 80</span></div>
            </Panel>
            <Panel title="失败类型分布" eyebrow="最新已完成任务">
              <FailureChart buckets={data.failureDistribution} />
            </Panel>
          </div>
          <Panel title="最近评测任务" eyebrow="任务与版本" action={<Link className="text-button" to={`/projects/${projectId}/evaluations`}>全部任务 <ArrowRight size={14} /></Link>}>
            <div className="table-wrap">
              <table>
                <thead><tr><th>任务</th><th>状态</th><th>数据集</th><th>版本</th><th>样本</th><th>综合分</th><th>更新时间</th><th /></tr></thead>
                <tbody>{data.recentTasks.map((task) => (
                  <tr key={task.id}>
                    <td><strong>{task.name}</strong><small>{task.id}</small></td>
                    <td><StatusBadge value={task.status} /></td>
                    <td>{task.datasetName}</td>
                    <td><code>{task.promptVersion}</code></td>
                    <td>{task.totalSamples}</td>
                    <td className="score-cell">{task.score ?? '—'}</td>
                    <td><span className="inline-icon"><CalendarRange size={14} />{formatDateTime(task.completedAt ?? task.createdAt)}</span></td>
                    <td>{task.status === 'completed' && <Link aria-label={`查看 ${task.name} 报告`} className="row-link" to={`/projects/${projectId}/evaluations/${task.id}/report`}><ArrowRight size={16} /></Link>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
      <Dialog open={trendOpen} title="质量与延迟趋势" eyebrow="LAST 7 EVALUATIONS" onClose={() => setTrendOpen(false)}>
        <TrendChart points={data.trend} />
        <div className="chart-legend"><span><i className="legend-blue" />综合质量分</span><span><i className="legend-muted" />目标线 80</span></div>
        <div className="table-wrap compact-table"><table><thead><tr><th>评测日期</th><th>综合质量分</th><th>端到端延迟</th><th>门禁</th></tr></thead><tbody>{data.trend.map((point) => <tr key={point.label}><td>{point.label}</td><td className="score-cell">{point.score}</td><td>{point.latencyMs}ms</td><td><StatusBadge value={point.score >= 80 ? 'passed' : 'failed'} /></td></tr>)}</tbody></table></div>
        <p className="form-hint">此弹窗展示当前项目概览已返回的趋势数据，不额外请求趋势服务。</p>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}
