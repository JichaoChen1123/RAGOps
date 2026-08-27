import { ArrowRight, Filter, Play, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { apiClient, apiMode } from '../api/client';
import { datasets as mockDatasets } from '../api/fixtures';
import { Dialog, Toast } from '../components/Interaction';
import { PageIntro, Panel } from '../components/Panel';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner, RefreshErrorBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { formatDateTime } from '../lib/format';
import type { Dataset, EvaluationTask, TaskStatus } from '../types';

type DisplayTask = EvaluationTask & { mockOnly?: boolean };
type TaskFilter = 'all' | TaskStatus;

const taskStatuses: { value: TaskFilter; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '运行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
];

export function EvaluationsPage() {
  const { projectId = 'demo' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<TaskFilter>('all');
  const [filterOpen, setFilterOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [localTasks, setLocalTasks] = useState<DisplayTask[] | null>(null);
  const [availableDatasets, setAvailableDatasets] = useState<Dataset[]>(apiMode === 'mock' ? mockDatasets : []);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    datasetId: apiMode === 'mock' ? mockDatasets[0]?.id ?? '' : '',
    modelVersion: 'qwen3-32b@2026-08',
    promptVersion: 'support-rag@v12',
    status: 'queued' as TaskStatus,
  });
  const { state, retry } = useApiResource(
    () => apiClient.listEvaluationTasks(projectId),
    [projectId],
    { scenario, emptyValue: [], partialize: (tasks) => tasks.map((task, index) => index === 0 ? { ...task, score: undefined, failedSamples: undefined } : task) },
  );

  useEffect(() => {
    if (state.status === 'success') setLocalTasks(state.data);
  }, [state]);

  useEffect(() => {
    void apiClient.listDatasets(projectId).then((items) => {
      const eligible = apiMode === 'api' ? items.filter((dataset) => dataset.status === 'ready') : items;
      setAvailableDatasets(eligible);
      setDraft((current) => eligible.some((dataset) => dataset.id === current.datasetId)
        ? current
        : { ...current, datasetId: eligible[0]?.id ?? '' });
    }).catch((error: unknown) => {
      setFeedback(error instanceof Error ? `数据集选项加载失败：${error.message}` : '数据集选项加载失败');
    });
  }, [projectId]);

  const allTasks: DisplayTask[] = localTasks ?? (state.status === 'success' ? state.data : []);
  const tasks = useMemo(() => allTasks.filter((task) => {
    const matchesQuery = `${task.name} ${task.datasetName} ${task.id}`.toLowerCase().includes(query.trim().toLowerCase());
    return matchesQuery && (statusFilter === 'all' || task.status === statusFilter);
  }), [allTasks, query, statusFilter]);

  if (state.status === 'loading') return <LoadingState label="正在同步评测任务" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;

  const refreshTasks = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshError(null);
    try {
      const refreshed = await apiClient.listEvaluationTasks(projectId);
      setLocalTasks(refreshed);
      setFeedback(apiMode === 'mock' ? 'Mock 任务状态已刷新' : '评测任务状态已从 API 刷新');
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : '发生未知错误，请稍后重试');
    } finally {
      setRefreshing(false);
    }
  };

  const createTask = async (event: FormEvent) => {
    event.preventDefault();
    const dataset = availableDatasets.find((item) => item.id === draft.datasetId) ?? availableDatasets[0];
    if (!dataset) return;
    setSaving(true);
    try {
      const response = await apiClient.createEvaluationTask(projectId, {
        datasetId: dataset.id,
        name: `${dataset.name} · ${apiMode === 'mock' ? 'Mock' : 'MVP'} 评测`,
        modelVersion: draft.modelVersion,
        promptVersion: draft.promptVersion,
      });
      const created: DisplayTask = apiMode === 'mock' ? {
        ...response,
        status: draft.status,
        progress: draft.status === 'completed' ? 100 : draft.status === 'running' ? 35 : 0,
        completedAt: draft.status === 'completed' ? new Date().toISOString() : undefined,
        failedSamples: draft.status === 'completed' ? 2 : undefined,
        score: draft.status === 'completed' ? 87.6 : undefined,
        mockOnly: true,
      } : { ...response, datasetName: dataset.name };
      setLocalTasks((current) => [created, ...(current ?? [])]);
      setCreateOpen(false);
      setFeedback(apiMode === 'mock'
        ? `已生成 ${taskStatuses.find((item) => item.value === created.status)?.label} Mock 任务`
        : `评测任务“${created.name}”已通过 API 创建，当前状态：${created.status}`);
    } catch (error) {
      setFeedback(error instanceof Error ? `创建失败：${error.message}` : '创建失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageIntro title="评测任务" description="按数据集、模型和 Prompt 版本追踪每次运行，并从完成任务进入证据化报告。" actions={<button className="button button-primary" type="button" onClick={() => setCreateOpen(true)}><Play size={15} />新建评测任务</button>} />
      <PartialDataBanner message={state.partialMessage} />
      <div className="summary-strip">
        <div><span>今日运行</span><strong>{allTasks.length}</strong></div>
        <div><span>进行中</span><strong>{allTasks.filter((task) => task.status === 'running').length}</strong></div>
        <div><span>失败样本</span><strong className="text-critical">{allTasks.reduce((sum, task) => sum + (task.failedSamples ?? 0), 0)}</strong></div>
        <div><span>平均通过分</span><strong>{allTasks.find((task) => task.score)?.score ?? '—'}</strong></div>
      </div>
      <Panel
        title={`任务列表（${allTasks.length}）`}
        eyebrow="EVALUATION RUNS"
        action={(
          <div className="toolbar">
            <label className="search-box"><Search size={15} /><input aria-label="搜索评测任务" placeholder="搜索任务或数据集" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
            <button className="button button-quiet" type="button" onClick={() => void refreshTasks()} disabled={refreshing} aria-busy={refreshing}>
              <RefreshCw className={refreshing ? 'icon-spin' : undefined} size={15} />{refreshing ? '刷新中' : '刷新任务状态'}
            </button>
            <div className="menu-anchor">
              <button className={`button button-quiet ${statusFilter !== 'all' ? 'filter-active' : ''}`} type="button" aria-expanded={filterOpen} onClick={() => setFilterOpen((value) => !value)}><Filter size={15} />筛选{statusFilter !== 'all' && ' · 1'}</button>
              {filterOpen && <div className="filter-popover"><label>任务状态<select aria-label="按状态筛选评测任务" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as TaskFilter)}>{taskStatuses.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><button type="button" onClick={() => { setStatusFilter('all'); setFilterOpen(false); }}>清除筛选</button></div>}
            </div>
          </div>
        )}
      >
        {refreshing && <div className="refresh-progress" role="status" aria-live="polite">正在刷新任务状态，当前列表与筛选保持可用。</div>}
        {refreshError && <RefreshErrorBanner subject="任务状态" message={refreshError} onRetry={() => void refreshTasks()} retrying={refreshing} />}
        {allTasks.length === 0 ? (
          <EmptyState title="还没有评测任务" description="选择已就绪的数据集、模型与 Prompt 版本，建立第一个质量基线。" action={<button className="button button-primary" type="button" onClick={() => setCreateOpen(true)}><Play size={15} />新建首个任务</button>} />
        ) : tasks.length === 0 ? (
          <EmptyState title="未找到匹配任务" description="尝试更换关键词或清除状态筛选。" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>任务</th><th>状态 / 进度</th><th>数据集</th><th>模型 / Prompt</th><th>样本</th><th>失败</th><th>综合分</th><th>创建时间</th><th /></tr></thead>
              <tbody>{tasks.map((task) => (
                <tr key={task.id}>
                  <td><strong>{task.name} {task.mockOnly && <em className="mock-label">MOCK</em>}</strong><small>{task.id}</small></td>
                  <td><StatusBadge value={task.status} />{task.status === 'running' && <div className="mini-progress"><i style={{ width: `${task.progress}%` }} /><span>{task.progress}%</span></div>}</td>
                  <td>{task.datasetName}</td>
                  <td><span className="stacked-code"><code>{task.modelVersion}</code><code>{task.promptVersion}</code></span></td>
                  <td>{task.totalSamples}</td>
                  <td className={task.failedSamples ? 'text-critical' : ''}>{task.failedSamples ?? '—'}</td>
                  <td className="score-cell">{task.score ?? '—'}</td>
                  <td>{formatDateTime(task.createdAt)}</td>
                  <td>{task.status === 'completed' && (task.mockOnly ? <button className="button button-small" type="button" onClick={() => setFeedback('Mock 任务仅演示创建结果，未生成服务端报告')}>Mock 结果</button> : <Link className="button button-small" to={`/projects/${projectId}/evaluations/${task.id}/report`}>查看报告 <ArrowRight size={14} /></Link>)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>

      <Dialog
        open={createOpen}
        title="新建评测任务"
        eyebrow={apiMode === 'mock' ? 'MOCK EVALUATION' : 'API EVALUATION'}
        onClose={() => setCreateOpen(false)}
        footer={<><button className="button button-secondary" type="button" onClick={() => setCreateOpen(false)}>取消</button><button className="button button-primary" type="submit" form="create-evaluation-form" disabled={saving || availableDatasets.length === 0}><Play size={15} />{apiMode === 'mock' ? '生成 Mock 任务' : '创建评测任务'}</button></>}
      >
        <form className="form-grid" id="create-evaluation-form" onSubmit={createTask}>
          <label>数据集<select aria-label="选择评测数据集" value={draft.datasetId} onChange={(event) => setDraft((current) => ({ ...current, datasetId: event.target.value }))}>{availableDatasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.sampleCount} 条</option>)}</select></label>
          <label>模拟初始状态<select aria-label="选择任务状态" value={draft.status} disabled={apiMode === 'api'} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value as TaskStatus }))}><option value="queued">排队中</option><option value="running">运行中（35%）</option><option value="completed">已完成（87.6 分）</option></select></label>
          <label>模型版本<select aria-label="选择模型版本" value={draft.modelVersion} onChange={(event) => setDraft((current) => ({ ...current, modelVersion: event.target.value }))}><option>qwen3-32b@2026-08</option><option>qwen3-14b@2026-08</option></select></label>
          <label>Prompt 版本<select aria-label="选择 Prompt 版本" value={draft.promptVersion} onChange={(event) => setDraft((current) => ({ ...current, promptVersion: event.target.value }))}><option>support-rag@v12</option><option>support-rag@v11</option><option>billing-rag@v7</option></select></label>
        </form>
        <p className="form-hint">{apiMode === 'mock' ? '任务会明确标记为 MOCK，并只保存在当前页面会话；不会调用真实模型或服务。' : availableDatasets.length === 0 ? 'API 中没有已发布数据集；请先通过后端发布一个草稿。' : '将调用 POST /evaluation-jobs；任务状态由后端确定性执行器推进。'}</p>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}
