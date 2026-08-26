import { ArrowRight, Filter, Play, Search } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import { PageIntro, Panel } from '../components/Panel';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { formatDateTime } from '../lib/format';

export function EvaluationsPage() {
  const { projectId = 'demo' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const [query, setQuery] = useState('');
  const { state, retry } = useApiResource(
    () => apiClient.listEvaluationTasks(projectId),
    [projectId],
    { scenario, emptyValue: [], partialize: (tasks) => tasks.map((task, index) => index === 0 ? { ...task, score: undefined, failedSamples: undefined } : task) },
  );
  const tasks = useMemo(() => state.status === 'success'
    ? state.data.filter((task) => `${task.name} ${task.datasetName}`.toLowerCase().includes(query.toLowerCase()))
    : [], [query, state]);

  if (state.status === 'loading') return <LoadingState label="正在同步评测任务" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;

  return (
    <>
      <PageIntro title="评测任务" description="按数据集、模型和 Prompt 版本追踪每次运行，并从完成任务进入证据化报告。" actions={<button className="button button-primary" type="button"><Play size={15} />新建评测任务</button>} />
      <PartialDataBanner message={state.partialMessage} />
      <div className="summary-strip">
        <div><span>今日运行</span><strong>{state.data.length}</strong></div>
        <div><span>进行中</span><strong>{state.data.filter((task) => task.status === 'running').length}</strong></div>
        <div><span>失败样本</span><strong className="text-critical">{state.data.reduce((sum, task) => sum + (task.failedSamples ?? 0), 0)}</strong></div>
        <div><span>平均通过分</span><strong>{state.data.find((task) => task.score)?.score ?? '—'}</strong></div>
      </div>
      <Panel title={`任务列表（${state.data.length}）`} eyebrow="EVALUATION RUNS" action={<div className="toolbar"><label className="search-box"><Search size={15} /><input aria-label="搜索评测任务" placeholder="搜索任务或数据集" value={query} onChange={(event) => setQuery(event.target.value)} /></label><button className="button button-quiet" type="button"><Filter size={15} />筛选</button></div>}>
        {state.data.length === 0 ? (
          <EmptyState title="还没有评测任务" description="选择已就绪的数据集、模型与 Prompt 版本，建立第一个质量基线。" action={<button className="button button-primary" type="button"><Play size={15} />新建首个任务</button>} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>任务</th><th>状态 / 进度</th><th>数据集</th><th>模型 / Prompt</th><th>样本</th><th>失败</th><th>综合分</th><th>创建时间</th><th /></tr></thead>
              <tbody>{tasks.map((task) => (
                <tr key={task.id}>
                  <td><strong>{task.name}</strong><small>{task.id}</small></td>
                  <td><StatusBadge value={task.status} />{task.status === 'running' && <div className="mini-progress"><i style={{ width: `${task.progress}%` }} /><span>{task.progress}%</span></div>}</td>
                  <td>{task.datasetName}</td>
                  <td><span className="stacked-code"><code>{task.modelVersion}</code><code>{task.promptVersion}</code></span></td>
                  <td>{task.totalSamples}</td>
                  <td className={task.failedSamples ? 'text-critical' : ''}>{task.failedSamples ?? '—'}</td>
                  <td className="score-cell">{task.score ?? '—'}</td>
                  <td>{formatDateTime(task.createdAt)}</td>
                  <td>{task.status === 'completed' && <Link className="button button-small" to={`/projects/${projectId}/evaluations/${task.id}/report`}>查看报告 <ArrowRight size={14} /></Link>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
