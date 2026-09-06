import {
  ArrowRight,
  BadgeCheck,
  Bot,
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
import { TaskStack } from '../components/TaskStack';
import { StatusBadge } from '../components/StatusBadge';
import { TrendChart } from '../components/TrendChart';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import type { EvaluationTask, ProjectOverview } from '../types';

const emptyOverview: ProjectOverview = {
  project: { id: 'demo', name: '客服 RAG 生产线', description: '', environment: 'production-shadow', updatedAt: new Date(0).toISOString() },
  metrics: [], recentTasks: [], failureDistribution: [], trend: [],
};

const pipelineSteps = [
  { label: 'Dataset', title: '数据集', detail: '固定版本 · 样本标签', state: 'READY', icon: Database },
  { label: 'Evaluation Job', title: '评测任务', detail: '执行器 · 运行快照', state: 'DONE', icon: Play },
  { label: 'Metrics', title: '指标计算', detail: '状态化结果 · 不补零', state: 'STATE', icon: Microscope },
  { label: 'Failure Diagnosis', title: '失败诊断', detail: '规则 · 可追溯证据', state: 'TRACE', icon: ScanSearch },
  { label: 'Report', title: '评测报告', detail: 'JSON · audit ready', state: 'READY', icon: FileCheck2 },
  { label: 'Review', title: '人工复核', detail: '确认 · 排除 · 反馈', state: 'OPEN', icon: BadgeCheck },
];

const capabilityGroups = [
  {
    label: 'METRICS',
    title: '多维质量评测',
    icon: Microscope,
    status: '状态可追溯',
    items: ['ok', 'not evaluated', 'unknown', 'error'],
  },
  {
    label: 'DIAGNOSIS RULES',
    title: '证据级故障归因',
    icon: ScanSearch,
    status: '证据分层',
    items: ['给定上下文', '本次检索', '来源未知', '引用支持性'],
  },
  {
    label: 'VERSION TRACE',
    title: '运行版本可追溯',
    icon: GitBranch,
    status: '快照固定',
    items: ['Dataset schema', 'Adapter', 'Prompt', 'Generation config'],
  },
  {
    label: 'DELIVERY GATE',
    title: '工程质量门禁',
    icon: ShieldCheck,
    status: '工程检查',
    items: ['TypeScript', 'Vitest', 'Build', 'No silent fallback'],
  },
];

function RuntimeContext({ task }: { task?: EvaluationTask }) {
  return (
    <section className="runtime-context" aria-label="当前评测运行上下文">
      <div><span className={`runtime-signal runtime-${apiMode}`}><i />{apiMode === 'mock' ? 'MOCK FIXTURE' : 'API DATA'}</span><small>前端数据源</small></div>
      <div><Bot size={15} /><span><strong>{task?.adapterId ?? '未知'}</strong><small>后端执行器</small></span></div>
      <div><GitBranch size={15} /><span><strong>{task?.modelVersion ?? '未知'}</strong><small>请求模型（来自快照）</small></span></div>
      <div><ShieldCheck size={15} /><span><strong>{task ? <StatusBadge value={task.qualityStatus} /> : '未知'}</strong><small>质量状态 / 非执行状态</small></span></div>
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
        eyebrow={apiMode === 'mock' ? 'OFFLINE FIXTURE WORKBENCH' : 'RAGOPS API WORKBENCH'}
        title={data.project.name}
        description="追踪任务执行、质量评估与样本证据；未知和未评估保持原样，不从运行成功推导质量。"
        actions={<><button className="button button-secondary" type="button" onClick={refreshOverview}><RefreshCw size={15} />刷新数据</button><Link className="button button-primary" to={`/projects/${projectId}/evaluations`}><Play size={15} />新建评测</Link></>}
      />
      <RuntimeContext task={data.recentTasks[0]} />
      <PartialDataBanner message={state.partialMessage} />
      {data.warnings?.map((warning) => <PartialDataBanner key={warning} message={warning} />)}
      <section className="recent-runs" aria-labelledby="recent-runs-title">
        <header className="section-heading"><div><h2 id="recent-runs-title">最近评测任务</h2><p>逐次检查执行、质量与运行版本。</p></div><Link className="text-button" to={`/projects/${projectId}/evaluations`}>全部任务 <ArrowRight size={14} /></Link></header>
        <TaskStack tasks={data.recentTasks} projectId={projectId} />
      </section>
      {data.metrics.length === 0 ? (
        <EmptyState title="暂无已评质量指标" description="任务执行记录与质量评估分别展示。" action={<Link className="button button-primary" to={`/projects/${projectId}/datasets`}>前往数据集</Link>} />
      ) : (
        <>
          <div className="metric-grid">{data.metrics.map((metric) => <MetricCard key={metric.key} metric={metric} />)}</div>
          <div className="dashboard-grid">
            <Panel title="质量趋势" eyebrow="仅展示已评估记录" action={<button className="text-button" type="button" onClick={() => setTrendOpen(true)}>查看趋势看板 <ArrowRight size={14} /></button>} className="panel-wide">
              <span id="quality-trends" className="anchor-target" />
              {data.trend.length > 0 ? <><TrendChart points={data.trend} /><div className="chart-legend"><span><i className="legend-blue" />已评质量分</span><span><i className="legend-muted" />报告记录</span></div></> : <EmptyState title="暂无可用质量趋势" description="执行成功但未做质量评估的任务不会生成 0 或 100 分趋势点。" />}
            </Panel>
            <Panel title="失败类型分布" eyebrow="最新已完成任务">
              <FailureChart buckets={data.failureDistribution} />
            </Panel>
          </div>
        </>
      )}
      {apiMode === 'mock' && data.metrics.length > 0 && <TechnicalCapabilities />}
      <Dialog open={trendOpen} title="质量与延迟趋势" eyebrow="LAST 7 EVALUATIONS" onClose={() => setTrendOpen(false)}>
        {data.trend.length > 0 ? <><TrendChart points={data.trend} /><div className="chart-legend"><span><i className="legend-blue" />已评质量分</span></div><div className="table-wrap compact-table"><table><thead><tr><th>评测日期</th><th>质量分</th><th>端到端延迟</th></tr></thead><tbody>{data.trend.map((point) => <tr key={point.label}><td>{point.label}</td><td className="score-cell">{point.score}</td><td>{point.latencyMs}ms</td></tr>)}</tbody></table></div></> : <EmptyState title="质量趋势未评估" description="当前记录只有执行结果，未生成语义质量分。" />}
        <p className="form-hint">只展示报告明确返回的质量分；不使用执行成功率推算质量，也不按阈值在浏览器补造门禁结论。</p>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}
