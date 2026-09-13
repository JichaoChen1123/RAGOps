import { ArrowRight, Filter, Play, PlugZap, RefreshCw, Search, ShieldCheck } from 'lucide-react';
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
import type { Dataset, DatasetSampleInput, EvaluationTask, ModelChannel, ModelExecutionStatus, TaskStatus } from '../types';

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

const diagnosticValue = (error: ApiError, key: string) => {
  const value = error.details?.[key];
  return typeof value === 'string' && value ? value : null;
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
  const [verifying, setVerifying] = useState<'authentication' | 'generation' | null>(null);
  const [pendingGenerationVerification, setPendingGenerationVerification] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelExecutionStatus | null>(null);
  const [datasetSamples, setDatasetSamples] = useState<DatasetSampleInput[]>([]);
  const [selectedSampleIds, setSelectedSampleIds] = useState<string[] | null>(null);
  const [draft, setDraft] = useState({
    datasetId: apiMode === 'mock' ? mockDatasets.find((item) => item.status === 'ready')?.id ?? '' : '',
    adapterId: 'mock' as ModelChannel,
    contextPolicy: 'dataset_contexts' as 'dataset_contexts' | 'none' | 'retrieval',
    model: 'mock-ragops-v1',
    promptVersion: 'support-rag@v12',
    promptText: '仅依据给定上下文回答；证据不足时明确说明。',
    reasoningEffort: 'low',
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
    void apiClient.getModelExecutionStatus().then(setModelStatus).catch(() => setModelStatus(null));
  }, []);

  useEffect(() => {
    if (!draft.datasetId) { setDatasetSamples([]); setSelectedSampleIds(null); return; }
    void apiClient.listDatasetSamples(projectId, draft.datasetId).then((items) => { setDatasetSamples(items); setSelectedSampleIds(null); }).catch(() => setDatasetSamples([]));
  }, [projectId, draft.datasetId]);

  const selectedProvider = modelStatus?.providers.find((provider) => provider.providerId === draft.adapterId);
  const selectedModel = selectedProvider?.models.find((model) => model.id === draft.model);
  const reasoningOptions = selectedModel?.reasoningEfforts.length
    ? selectedModel.reasoningEfforts
    : ['low', 'medium', 'high'];

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
        sampleIds: selectedSampleIds ?? undefined,
        name: `${dataset.name} · ${draft.adapterId === 'mock' ? '模拟' : draft.adapterId === 'codex_chatgpt' ? 'Codex 账号' : 'OpenAI 兼容'}评测`,
        adapterId: draft.adapterId,
        prompt: { version: draft.promptVersion, text: draft.promptText },
        generation: {
          model: draft.model,
          temperature: 0,
          topP: 1,
          maxOutputTokens: 512,
          stop: [],
          seed: null,
          reasoningEffort: draft.adapterId === 'codex_chatgpt' ? draft.reasoningEffort : null,
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

  const changeAdapter = (adapterId: ModelChannel) => {
    setPendingGenerationVerification(false);
    const provider = modelStatus?.providers.find((item) => item.providerId === adapterId);
    const providerModel = provider?.defaultModel
      ?? provider?.models.find((model) => model.isDefault)?.id
      ?? provider?.models[0]?.id;
    const providerReasoning = provider?.models.find((model) => model.id === providerModel)?.reasoningEfforts[0];
    setDraft((current) => ({
      ...current,
      adapterId,
      model: adapterId === 'mock'
        ? 'mock-ragops-v1'
        : providerModel ?? (adapterId === 'codex_chatgpt' ? '' : 'provider-model'),
      reasoningEffort: providerReasoning ?? 'low',
    }));
  };

  const verifyProvider = async (performGeneration: boolean) => {
    if (draft.adapterId === 'mock' || apiMode === 'mock' || verifying) return;
    setVerifying(performGeneration ? 'generation' : 'authentication');
    try {
      const result = await apiClient.verifyModelProvider(draft.adapterId, {
        model: draft.model || undefined,
        performGeneration,
      });
      const refreshed = await apiClient.getModelExecutionStatus();
      setModelStatus(refreshed);
      const defaultModel = result.models.find((model) => model.isDefault) ?? result.models[0];
      if (!draft.model && defaultModel) setDraft((current) => ({
        ...current,
        model: defaultModel.id,
        reasoningEffort: defaultModel.reasoningEfforts[0] ?? current.reasoningEffort,
      }));
      setFeedback(`${result.message}${result.warning ? ` ${result.warning}` : ''}`);
    } catch (error) {
      const code = error instanceof ApiError && error.code ? ` [${error.code}]` : '';
      const reasonCode = error instanceof ApiError ? diagnosticValue(error, 'reason_code') : null;
      const diagnosticId = error instanceof ApiError ? diagnosticValue(error, 'diagnostic_id') : null;
      const diagnostic = [
        reasonCode ? `原因 ${reasonCode}` : null,
        diagnosticId ? `诊断 ID ${diagnosticId}` : null,
      ].filter(Boolean).join(' · ');
      setFeedback(error instanceof Error
        ? `验证失败${code}${diagnostic ? `（${diagnostic}）` : ''}：${error.message}`
        : '验证失败，请检查后端配置');
    } finally {
      setVerifying(null);
    }
  };

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
        onClose={() => { setCreateOpen(false); setPendingGenerationVerification(false); }}
        footer={<><button className="button button-secondary" type="button" onClick={() => setCreateOpen(false)}>取消</button><button className="button button-primary" type="submit" form="create-evaluation-form" disabled={saving || availableDatasets.length === 0 || (selectedSampleIds !== null && selectedSampleIds.length === 0)}><Play size={15} />创建评测任务（{(selectedSampleIds?.length ?? datasetSamples.length) || availableDatasets.find((item) => item.id === draft.datasetId)?.sampleCount || 0} 条）</button></>}
      >
        <form className="form-grid" id="create-evaluation-form" onSubmit={createTask}>
          <label>已发布数据集<select aria-label="选择评测数据集" value={draft.datasetId} onChange={(event) => setDraft((current) => ({ ...current, datasetId: event.target.value }))}>{availableDatasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.sampleCount} 条</option>)}</select></label>
          <fieldset className="field-full"><legend>评测样本（{selectedSampleIds?.length ?? datasetSamples.length} / {datasetSamples.length || availableDatasets.find((item) => item.id === draft.datasetId)?.sampleCount || 0}）</legend><label><input type="radio" checked={selectedSampleIds === null} onChange={() => setSelectedSampleIds(null)} /> 全部样本</label><label><input type="radio" checked={selectedSampleIds !== null} onChange={() => setSelectedSampleIds(datasetSamples.map((item) => item.sampleId))} /> 选择部分</label>{selectedSampleIds !== null && <div className="sample-picker">{datasetSamples.map((sample) => <label key={sample.sampleId}><input type="checkbox" checked={selectedSampleIds.includes(sample.sampleId)} onChange={() => setSelectedSampleIds((current) => current?.includes(sample.sampleId) ? current.filter((id) => id !== sample.sampleId) : [...(current ?? []), sample.sampleId])} />{sample.question}</label>)}</div>}{selectedSampleIds !== null && selectedSampleIds.length === 0 && <p className="form-hint">请至少选择一条样本；空选择不会提交。</p>}</fieldset>
          <label>模型通道<select aria-label="选择后端执行器" value={draft.adapterId} onChange={(event) => changeAdapter(event.target.value as ModelChannel)}><option value="mock">mock（离线模拟）</option><option value="codex_chatgpt">codex_chatgpt（ChatGPT 登录）</option><option value="openai_compatible">openai_compatible（API Key）</option></select></label>
          <label>上下文策略<select aria-label="选择上下文策略" value={draft.contextPolicy} onChange={(event) => setDraft((current) => ({ ...current, contextPolicy: event.target.value as typeof current.contextPolicy }))}><option value="dataset_contexts">dataset_contexts（给定上下文）</option><option value="none">none（不提供上下文）</option><option value="retrieval">retrieval（本阶段不可用）</option></select></label>
          <label>请求模型{draft.adapterId === 'codex_chatgpt' && selectedProvider?.models.length ? <select aria-label="请求模型" value={draft.model} onChange={(event) => { const model = selectedProvider.models.find((item) => item.id === event.target.value); setDraft((current) => ({ ...current, model: event.target.value, reasoningEffort: model?.reasoningEfforts[0] ?? current.reasoningEffort })); }}>{selectedProvider.models.map((model) => <option key={model.id} value={model.id}>{model.displayName}{model.isDefault ? '（默认）' : ''}</option>)}</select> : <input required aria-label="请求模型" value={draft.model} onChange={(event) => setDraft((current) => ({ ...current, model: event.target.value }))} />}</label>
          {draft.adapterId === 'codex_chatgpt' && <label>推理强度<select aria-label="Codex 推理强度" value={draft.reasoningEffort} onChange={(event) => setDraft((current) => ({ ...current, reasoningEffort: event.target.value }))}>{reasoningOptions.map((effort) => <option key={effort} value={effort}>{effort}</option>)}</select></label>}
          <label>Prompt 版本<input aria-label="Prompt 版本" value={draft.promptVersion} onChange={(event) => setDraft((current) => ({ ...current, promptVersion: event.target.value }))} /></label>
          <label className="field-full">Prompt 文本<textarea required aria-label="Prompt 文本" value={draft.promptText} onChange={(event) => setDraft((current) => ({ ...current, promptText: event.target.value }))} /></label>
        </form>
        {draft.adapterId !== 'mock' && <div className="channel-status" aria-label="所选模型通道状态"><div><strong>{selectedProvider?.providerName ?? draft.adapterId}</strong><span>{selectedProvider?.configurationStatus ?? '状态未知'} · 登录 {selectedProvider?.authenticationStatus ?? 'unknown'} · 最近验证 {selectedProvider?.verificationStatus ?? 'unknown'} · 真实生成 {selectedProvider?.generationVerified ? '已验证' : '未验证'}</span><small>{selectedProvider?.verificationErrorCode ? `${selectedProvider.verificationErrorCode} · ` : ''}{selectedProvider?.verificationReasonCode ? `原因 ${selectedProvider.verificationReasonCode} · ` : ''}{selectedProvider?.verificationDiagnosticId ? `诊断 ID ${selectedProvider.verificationDiagnosticId} · ` : ''}{selectedProvider?.verificationMessage ?? selectedProvider?.protocol ?? '协议未知'}{selectedProvider?.codexVersion ? ` · ${selectedProvider.codexVersion}` : ''}</small></div><div className="channel-actions">{draft.adapterId === 'codex_chatgpt' && <button className="button button-secondary" type="button" disabled={apiMode === 'mock' || verifying !== null} onClick={() => void verifyProvider(false)}><ShieldCheck size={15} />{verifying === 'authentication' ? '检查中' : '检查登录'}</button>}<button className="button button-secondary" type="button" disabled={apiMode === 'mock' || verifying !== null || !draft.model} onClick={() => setPendingGenerationVerification(true)}><PlugZap size={15} />{verifying === 'generation' ? '验证中' : draft.adapterId === 'codex_chatgpt' ? '真实小请求验证' : '付费小请求验证'}</button></div></div>}
        {pendingGenerationVerification && draft.adapterId !== 'mock' && <div className="verification-confirm" role="alertdialog" aria-label="确认真实小请求验证"><ShieldCheck size={20} /><div><strong>确认发起真实小请求</strong><p>{draft.adapterId === 'codex_chatgpt' ? '这会使用当前 ChatGPT 账号可用的 Codex 权益；超时不会自动重提。' : '这会调用已配置的 OpenAI-compatible 提供方，可能产生费用。'}失败时不会切换到其他通道。</p></div><div><button className="button button-secondary" type="button" onClick={() => setPendingGenerationVerification(false)}>取消</button><button className="button button-primary" type="button" onClick={() => { setPendingGenerationVerification(false); void verifyProvider(true); }}>确认验证</button></div></div>}
        <p className="form-hint">{availableDatasets.length === 0 ? '当前没有已发布数据集；请先完成样本导入和发布。' : apiMode === 'mock' && draft.adapterId !== 'mock' ? '前端 Mock 数据模式不会连接真实模型通道；请先把 VITE_API_MODE 切换为 api。' : draft.adapterId === 'codex_chatgpt' ? '登录检查不生成内容；真实小请求会使用账号可用的 Codex 权益。不会转成通用 API 余额，也不会自动改走收费 API。' : draft.adapterId === 'openai_compatible' ? '当前只支持 Chat Completions；Base URL 是 API 根（通常含 /v1）。验证请求可能产生服务商费用，凭据仅由后端读取。' : 'Mock 执行器不会发外部请求；任务执行成功后，未配置质量门仍显示“质量未评估 / 分数未知”。'}</p>
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}
