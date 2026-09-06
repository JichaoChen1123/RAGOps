import { ArrowRight, Filter, Play, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useOutletContext, useParams } from 'react-router-dom';
import { ApiError, apiClient, apiMode } from '../api/client';
import { datasets as mockDatasets } from '../api/fixtures';
import { Dialog, Toast } from '../components/Interaction';
import { PageIntro, Panel } from '../components/Panel';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner, RefreshErrorBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { formatDateTime } from '../lib/format';
import type { Dataset, EvaluationTask, ExecutionAdapterId, ModelExecutionStatus, TaskStatus } from '../types';

type TaskFilter = 'all' | TaskStatus;

const taskStatuses: { value: TaskFilter; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '运行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
];

const isTerminal = (status: TaskStatus) => status === 'completed' || status === 'failed' || status === 'cancelled';
const adapterLabels: Record<ExecutionAdapterId, string> = {
  mock: '模拟',
  codex_chatgpt: 'Codex ChatGPT',
  openai_compatible: 'OpenAI-compatible',
};

export function EvaluationsPage() {
  const { projectId = 'demo' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<TaskFilter>('all');
  const [filterOpen, setFilterOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [localTasks, setLocalTasks] = useState<EvaluationTask[] | null>(null);
  const [availableDatasets, setAvailableDatasets] = useState<Dataset[]>(apiMode === 'mock' ? mockDatasets.filter((item) => item.status === 'ready') : []);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelExecutionStatus | null>(null);
  const [modelStatusError, setModelStatusError] = useState<string | null>(null);
  const [draft, setDraft] = useState({
    datasetId: apiMode === 'mock' ? mockDatasets.find((item) => item.status === 'ready')?.id ?? '' : '',
    adapterId: 'mock' as ExecutionAdapterId,
    contextPolicy: 'dataset_contexts' as 'dataset_contexts' | 'none' | 'retrieval',
    model: 'mock-ragops-v1',
    promptVersion: 'support-rag@v12',
    promptText: '仅依据给定上下文回答；证据不足时明确说明。',
  });
  const { state, retry } = useApiResource(
    () => apiClient.listEvaluationTasks(projectId),
    [projectId],
    {
      scenario,
      emptyValue: [],
      partialize: (tasks) => tasks.map((task, index) => index === 0
        ? { ...task, qualityStatus: 'partial', qualityVerdict: 'unknown', qualityScore: null }
        : task),
    },
  );

  useEffect(() => {
    if (state.status === 'success') setLocalTasks(state.data);
  }, [state]);

  useEffect(() => {
    void apiClient.listDatasets(projectId).then((items) => {
      const eligible = items.filter((dataset) => dataset.status === 'ready');
      setAvailableDatasets(eligible);
      setDraft((current) => eligible.some((dataset) => dataset.id === current.datasetId)
        ? current
        : { ...current, datasetId: eligible[0]?.id ?? '' });
    }).catch((error: unknown) => {
      setFeedback(error instanceof Error ? `数据集选项加载失败：${error.message}` : '数据集选项加载失败');
    });
  }, [projectId]);

  useEffect(() => {
    let active = true;
    void apiClient.getModelExecutionStatus().then((status) => {
      if (active) {
        setModelStatus(status);
        setModelStatusError(null);
      }
    }).catch((error: unknown) => {
      if (active) setModelStatusError(error instanceof Error ? error.message : '模型通道状态读取失败');
    });
    return () => { active = false; };
  }, []);

  const allTasks = localTasks ?? (state.status === 'success' ? state.data : []);
  const tasks = useMemo(() => allTasks.filter((task) => {
    const matchesQuery = `${task.name} ${task.datasetName} ${task.id}`.toLowerCase().includes(query.trim().toLowerCase());
    return matchesQuery && (statusFilter === 'all' || task.status === statusFilter);
  }), [allTasks, query, statusFilter]);
  const evaluatedScores = allTasks.map((task) => task.qualityScore).filter((score): score is number => score !== null);
  const averageQualityScore = evaluatedScores.length > 0
    ? (evaluatedScores.reduce((sum, score) => sum + score, 0) / evaluatedScores.length).toFixed(1)
    : '未知';

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
    const dataset = availableDatasets.find((item) => item.id === draft.datasetId);
    if (!dataset) return;
    setSaving(true);
    try {
      const created = await apiClient.createEvaluationTask(projectId, {
        datasetId: dataset.id,
        name: `${dataset.name} · ${adapterLabels[draft.adapterId]}评测`,
        adapterId: draft.adapterId,
        prompt: { version: draft.promptVersion, text: draft.promptText },
        generation: {
          model: draft.model,
          temperature: 0,
          topP: 1,
          maxOutputTokens: 512,
          stop: [],
          seed: null,
        },
        contextPolicy: draft.contextPolicy,
        metrics: [],
        qualityGate: null,
      });
      setLocalTasks((current) => [{ ...created, datasetName: dataset.name }, ...(current ?? [])]);
      setCreateOpen(false);
      setFeedback(apiMode === 'mock'
        ? `已创建明确标记的 Mock 任务；质量保持未评估`
        : `任务“${created.name}”已由后端接受；执行器 ${created.adapterId ?? '未知'}，质量 ${created.qualityStatus}`);
    } catch (error) {
      const code = error instanceof ApiError && error.code ? ` [${error.code}]` : '';
      setFeedback(error instanceof Error ? `创建失败${code}：${error.message}` : '创建失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  const changeAdapter = (adapterId: ExecutionAdapterId) => {
    const provider = modelStatus?.providers.find((item) => item.adapterId === adapterId || item.providerId === adapterId);
    setDraft((current) => ({
      ...current,
      adapterId,
      model: adapterId === 'mock' ? 'mock-ragops-v1' : provider?.availableModels?.[0] ?? '',
    }));
  };

  const selectedProvider = modelStatus?.providers.find((item) => item.adapterId === draft.adapterId || item.providerId === draft.adapterId);
  const modelOptions = selectedProvider?.availableModels ?? [];

  return (
    <>
      <PageIntro title="评测任务" description="分别追踪任务生命周期、样本执行结果和质量状态；执行成功不会自动变成质量通过。" actions={<button className="button button-primary" type="button" onClick={() => setCreateOpen(true)}><Play size={15} />新建评测任务</button>} />
      <PartialDataBanner message={state.partialMessage} />
      <div className="summary-strip">
        <div><span>任务总数</span><strong>{allTasks.length}</strong></div>
        <div><span>进行中</span><strong>{allTasks.filter((task) => task.status === 'running').length}</strong></div>
        <div><span>执行失败样本</span><strong className="text-critical">{allTasks.reduce((sum, task) => sum + task.failedSamples, 0)}</strong></div>
        <div><span>已评质量分</span><strong>{averageQualityScore}</strong></div>
      </div>
      <Panel
        title={`任务列表（${allTasks.length}）`}
        eyebrow="LIFECYCLE / EXECUTION / QUALITY"
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
          <EmptyState title="还没有评测任务" description="先发布包含样本的数据集，再显式选择执行器创建任务。" action={<button className="button button-primary" type="button" onClick={() => setCreateOpen(true)}><Play size={15} />新建首个任务</button>} />
        ) : tasks.length === 0 ? (
          <EmptyState title="未找到匹配任务" description="尝试更换关键词或清除状态筛选。" />
        ) : (
          <div className="table-wrap" tabIndex={0} role="region" aria-label="评测任务表格，可横向滚动查看完整字段与操作">
            <table>
              <thead><tr><th>任务</th><th>生命周期</th><th>执行结果</th><th>质量状态</th><th>执行器 / 模型</th><th>样本</th><th>质量分</th><th>创建时间</th><th /></tr></thead>
              <tbody>{tasks.map((task) => (
                <tr key={task.id}>
                  <td><strong>{task.name} {task.isMock === true && <em className="mock-label">SIMULATED</em>}</strong><small>{task.id}</small></td>
                  <td><StatusBadge value={task.status} />{task.status === 'running' && <div className="mini-progress"><i style={{ width: `${task.progress}%` }} /><span>{task.progress}%</span></div>}</td>
                  <td>{task.outcome ? <StatusBadge value={task.outcome} /> : <span className="unknown-value">尚无结果</span>}<small>{task.succeededSamples} 成功 / {task.failedSamples} 失败</small></td>
                  <td><StatusBadge value={task.qualityStatus} /><small>结论：{task.qualityVerdict === 'unknown' ? '未知' : task.qualityVerdict === 'passed' ? '通过' : '不通过'}</small></td>
                  <td><span className="stacked-code"><code>{task.adapterId ?? '未知执行器'}</code><code>{task.modelVersion ?? '模型未知'}</code></span></td>
                  <td>{task.totalSamples}</td>
                  <td className="score-cell">{task.qualityScore ?? '未知'}</td>
                  <td>{formatDateTime(task.createdAt)}</td>
                  <td>{isTerminal(task.status) && <Link className="button button-small" to={`/projects/${projectId}/evaluations/${task.id}/report`}>查看报告 <ArrowRight size={14} /></Link>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>

      <Dialog
        open={createOpen}
        title="新建评测任务"
        eyebrow={apiMode === 'mock' ? 'MOCK FRONTEND' : 'API EVALUATION'}
        onClose={() => setCreateOpen(false)}
        footer={<><button className="button button-secondary" type="button" onClick={() => setCreateOpen(false)}>取消</button><button className="button button-primary" type="submit" form="create-evaluation-form" disabled={saving || availableDatasets.length === 0 || draft.model.trim().length === 0}><Play size={15} />创建评测任务</button></>}
      >
        <form className="form-grid" id="create-evaluation-form" onSubmit={createTask}>
          <label>已发布数据集<select aria-label="选择评测数据集" value={draft.datasetId} onChange={(event) => setDraft((current) => ({ ...current, datasetId: event.target.value }))}>{availableDatasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.sampleCount} 条</option>)}</select></label>
          <label>后端执行通道<select aria-label="选择后端执行通道" value={draft.adapterId} onChange={(event) => changeAdapter(event.target.value as ExecutionAdapterId)}><option value="mock">mock（离线模拟）</option><option value="codex_chatgpt">codex_chatgpt（ChatGPT 登录）</option><option value="openai_compatible">openai_compatible（Chat Completions）</option></select></label>
          <label>上下文策略<select aria-label="选择上下文策略" value={draft.contextPolicy} onChange={(event) => setDraft((current) => ({ ...current, contextPolicy: event.target.value as typeof current.contextPolicy }))}><option value="dataset_contexts">dataset_contexts（给定上下文）</option><option value="none">none（不提供上下文）</option><option value="retrieval">retrieval（本阶段不可用）</option></select></label>
          <label>请求模型<input required aria-label="请求模型" list="available-evaluation-models" placeholder={draft.adapterId === 'mock' ? undefined : '输入或选择后端允许的模型 ID'} value={draft.model} onChange={(event) => setDraft((current) => ({ ...current, model: event.target.value }))} /><datalist id="available-evaluation-models">{modelOptions.map((model) => <option key={model} value={model} />)}</datalist></label>
          <label>Prompt 版本<input aria-label="Prompt 版本" value={draft.promptVersion} onChange={(event) => setDraft((current) => ({ ...current, promptVersion: event.target.value }))} /></label>
          <label className="field-full">Prompt 文本<textarea required aria-label="Prompt 文本" value={draft.promptText} onChange={(event) => setDraft((current) => ({ ...current, promptText: event.target.value }))} /></label>
        </form>
        <div className="task-channel-summary field-full" aria-label="任务通道摘要"><span><small>前端数据</small><strong>{apiMode === 'mock' ? 'Mock fixture' : 'API 数据'}</strong></span><span><small>本任务执行通道</small><strong>{draft.adapterId}</strong></span><span><small>配置状态</small><strong>{selectedProvider?.configurationStatus ?? (draft.adapterId === 'mock' ? '内置可用' : '未知')}</strong></span><span><small>真实生成</small><strong>{draft.adapterId === 'mock' ? '不适用' : selectedProvider?.realGenerationVerified === true ? '已验证' : selectedProvider?.realGenerationVerified === false ? '未验证' : '未知'}</strong></span></div>
        {modelStatusError && <p className="form-hint">通道状态读取失败：{modelStatusError}。仍可显式提交，后端将进行最终校验；前端不会猜测通道可用。</p>}
        <p className="form-hint">{availableDatasets.length === 0 ? '当前没有已发布数据集；请先完成样本导入和发布。' : draft.adapterId === 'mock' ? 'Mock 通道不会发外部请求；任务执行成功后，未配置质量门仍显示“质量未评估 / 分数未知”。' : draft.adapterId === 'codex_chatgpt' ? 'Codex ChatGPT 通道由 Windows 主机登录和后端桥接执行；浏览器不接触 OAuth Token，失败也不会回退到其他通道。' : 'OpenAI-compatible 通道只提交模型 ID 和生成参数；浏览器不持有 API Key，失败也不会回退到 mock。'}</p>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}
