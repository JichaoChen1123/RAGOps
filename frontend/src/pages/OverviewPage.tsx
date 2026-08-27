import { ArrowRight, CalendarRange, Play, RefreshCw } from 'lucide-react';
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
      <PartialDataBanner message={state.partialMessage} />
      {data.metrics.length === 0 ? (
        <EmptyState title="尚无评测数据" description="创建首个数据集并运行评测后，这里将展示项目质量基线。" action={<Link className="button button-primary" to={`/projects/${projectId}/datasets`}>前往数据集</Link>} />
      ) : (
        <>
          <div className="metric-grid">{data.metrics.map((metric) => <MetricCard key={metric.key} metric={metric} />)}</div>
          <div className="dashboard-grid">
            <Panel title="质量趋势" eyebrow="最近 7 次评测" action={<button className="text-button" type="button" onClick={() => setTrendOpen(true)}>查看趋势看板 <ArrowRight size={14} /></button>} className="panel-wide">
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
