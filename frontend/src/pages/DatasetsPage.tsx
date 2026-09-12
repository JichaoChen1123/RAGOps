import { Archive, Copy, Eye, FilePlus2, Filter, MoreHorizontal, RefreshCw, Search, Upload } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { useOutletContext, useParams } from 'react-router-dom';
import { apiClient, apiMode } from '../api/client';
import { Dialog, Toast } from '../components/Interaction';
import { PageIntro, Panel } from '../components/Panel';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner, RefreshErrorBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { copyText } from '../lib/browser';
import { formatDateTime } from '../lib/format';
import { parseDatasetJsonl } from '../lib/jsonlDataset';
import { clearDatasetImportRecovery, loadDatasetImportRecovery, sameImportContent, sampleFingerprint, saveDatasetImportRecovery, type DatasetImportRecovery } from '../lib/datasetImportRecovery';
import type { Dataset, DatasetSampleInput, DatasetStatus } from '../types';

type DisplayDataset = Dataset & { mockOnly?: boolean; archived?: boolean };
type DatasetDialog = 'import' | 'create' | 'details' | null;
type DatasetFilter = 'all' | DatasetStatus;

const statusOptions: { value: DatasetFilter; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'ready', label: '可用' },
  { value: 'indexing', label: '索引中' },
  { value: 'draft', label: '草稿' },
  { value: 'failed', label: '失败' },
];

const exampleSamples: DatasetSampleInput[] = Array.from({ length: 12 }, (_, index) => {
  const suffix = String(index + 1).padStart(2, '0');
  const docId = `doc-refund-policy-${suffix}`;
  const chunkId = `chunk-refund-policy-${suffix}`;
  return {
    sampleId: `refund-example-${suffix}`,
    question: index === 0 ? '退款后成长值如何处理？' : `退款政策示例问题 ${index + 1}`,
    labels: {
      referenceAnswer: index === 0 ? '按退款金额比例扣回。' : `人工构造参考答案 ${index + 1}`,
      goldDocumentIds: [docId],
      goldEvidenceIds: [`evidence-refund-${suffix}`],
      expectedDiagnoses: [],
    },
    contexts: [{
      origin: 'provided',
      rank: 1,
      retrievalRunId: null,
      docId,
      chunkId,
      evidenceIds: [`evidence-refund-${suffix}`],
      text: index === 0 ? '退款成功后，成长值按退款商品实付金额比例扣回。' : `人工构造退款政策片段 ${index + 1}`,
      score: null,
      relevanceGrade: 3,
      usefulness: true,
    }],
    historicalOutput: null,
    tags: ['synthetic', 'refund'],
    metadata: { fixture_version: 'offline-example-v2' },
  };
});

export function DatasetsPage() {
  const { projectId = 'demo' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<DatasetFilter>('all');
  const [filterOpen, setFilterOpen] = useState(false);
  const [dialog, setDialog] = useState<DatasetDialog>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [localDatasets, setLocalDatasets] = useState<DisplayDataset[] | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [importSamples, setImportSamples] = useState<DatasetSampleInput[] | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importName, setImportName] = useState('');
  const [importFileName, setImportFileName] = useState('local.jsonl');
  const [importProgress, setImportProgress] = useState<{ datasetId: string; created: boolean; imported: boolean } | null>(null);
  const [importRecovery, setImportRecovery] = useState<DatasetImportRecovery | null>(null);
  const [pendingImport, setPendingImport] = useState<{ samples: DatasetSampleInput[]; name: string; fileName: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [publishingId, setPublishingId] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name: '', description: '', owner: '当前用户' });
  const { state, retry } = useApiResource(
    () => apiClient.listDatasets(projectId),
    [projectId],
    { scenario, emptyValue: [], partialize: (data) => data.slice(0, 2) },
  );

  useEffect(() => {
    if (state.status === 'success') setLocalDatasets(state.data);
  }, [state]);

  useEffect(() => {
    const recovery = loadDatasetImportRecovery(projectId);
    if (!recovery || recovery.imported) return;
    setImportRecovery(recovery);
    setImportProgress({ datasetId: recovery.datasetId, created: recovery.created, imported: recovery.imported });
    setImportSamples(recovery.samples);
    setImportName(recovery.name);
    setImportFileName(recovery.fileName);
  }, [projectId]);

  const datasets: DisplayDataset[] = localDatasets ?? (state.status === 'success' ? state.data : []);
  const filtered = useMemo(() => datasets.filter((dataset) => {
    const matchesQuery = `${dataset.name} ${dataset.description} ${dataset.id}`.toLowerCase().includes(query.trim().toLowerCase());
    return matchesQuery && (statusFilter === 'all' || dataset.status === statusFilter);
  }), [datasets, query, statusFilter]);
  const selectedDataset = datasets.find((dataset) => dataset.id === selectedDatasetId);

  if (state.status === 'loading') return <LoadingState label="正在载入数据集" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;

  const refreshDatasets = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshError(null);
    try {
      const refreshed = await apiClient.listDatasets(projectId);
      setLocalDatasets(refreshed);
      setFeedback(apiMode === 'mock' ? 'Mock 数据集列表已刷新' : '数据集列表已从 API 刷新');
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : '发生未知错误，请稍后重试');
    } finally {
      setRefreshing(false);
    }
  };

  const ensureMockArchive = () => {
    if (apiMode === 'mock') return true;
    setFeedback('LIVE API 尚未提供数据集归档接口；创建与示例导入可正常写入');
    return false;
  };

  const applyParsedImport = (samples: DatasetSampleInput[], name: string, fileName = 'local.jsonl') => {
    setImportSamples(samples); setImportError(null); setImportName(name); setPendingImport(null);
    setImportFileName(fileName); setImportProgress(null); setImportRecovery(null);
  };

  const receiveJsonl = async (file: File | undefined) => {
    if (!file) return;
    const parsed = parseDatasetJsonl(await file.text());
    setImportError(parsed.error);
    if (parsed.error) { setImportSamples(null); return; }
    const name = file.name.replace(/\.jsonl$/i, '') || '本地 JSONL 数据集';
    if (importRecovery && !sameImportContent(parsed.samples, importRecovery.samples)) {
      setPendingImport({ samples: parsed.samples, name, fileName: file.name });
      return;
    }
    if (importRecovery) {
      // Re-selecting the same file is a resume action. Keep its draft ID and
      // progress instead of letting applyParsedImport clear recovery state.
      setImportSamples(parsed.samples);
      setImportError(null);
      setImportName(importRecovery.name);
      setImportFileName(file.name);
      setImportProgress({ datasetId: importRecovery.datasetId, created: importRecovery.created, imported: importRecovery.imported });
      setPendingImport(null);
      return;
    }
    applyParsedImport(parsed.samples, name, file.name);
  };

  const importExample = async () => {
    setSaving(true);
    try {
      const created = await apiClient.createDataset(projectId, {
        name: '退款政策示例 JSONL',
        description: apiMode === 'mock'
          ? '[Mock 导入] 12 条退款政策问答样本，仅保存在当前页面会话。'
          : '通过 RAGOps 示例导入创建的 12 条退款政策问答草稿。',
        owner: '当前用户',
        version: 'v0.1',
      });
      const imported = await apiClient.importDatasetSamples(projectId, created.id, exampleSamples);
      // Import intentionally leaves the new dataset as a draft; publishing is a separate action.
      setLocalDatasets((current) => [{ ...imported.dataset, mockOnly: apiMode === 'mock' }, ...(current ?? [])]);
      setDialog(null);
      setFeedback(apiMode === 'mock'
        ? 'Mock 示例已完成创建、导入 12 条 2.0 样本并发布（仅当前会话）'
        : '示例数据集已通过 API 创建、导入 12 条 2.0 样本并发布');
    } catch (error) {
      setFeedback(error instanceof Error ? `导入失败：${error.message}` : '导入失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  const importLocalFile = async () => {
    if (!importSamples || saving) return;
    let recoveryForAttempt: DatasetImportRecovery | null = importRecovery;
    setSaving(true);
    try {
      if (importRecovery?.created) {
        // A resumed import always checks the draft before writing. This avoids
        // appending to a partially imported dataset after a lost response.
        const saved = await apiClient.listDatasetSamples(projectId, importRecovery.datasetId);
        if (sameImportContent(importSamples, saved)) {
          const dataset = await apiClient.getDataset(projectId, importRecovery.datasetId);
          clearDatasetImportRecovery(projectId);
          setImportRecovery(null);
          setImportProgress({ datasetId: importRecovery.datasetId, created: true, imported: true });
          setLocalDatasets((current) => [{ ...dataset, mockOnly: apiMode === 'mock' }, ...(current ?? []).filter((item) => item.id !== dataset.id)]);
          setFeedback('The draft already contains this file; no second import was sent. It remains a draft.');
          setDialog(null);
          return;
        }
        if (saved.length) {
          setImportError('The saved draft contains different samples. Import stopped without appending or overwriting it.');
          return;
        }
      }
      const datasetId = importRecovery?.created ? importRecovery.datasetId : (await apiClient.createDataset(projectId, {
        name: importName.trim() || '本地 JSONL 数据集', description: '由本地 JSONL 预检后导入的草稿。', owner: '当前用户', version: 'v0.1',
      })).id;
      setImportProgress({ datasetId, created: true, imported: false });
      const recovery: DatasetImportRecovery = { datasetId, created: true, imported: false, name: importName, fileName: importRecovery?.fileName ?? importFileName, fingerprint: sampleFingerprint(importSamples), samples: importSamples };
      recoveryForAttempt = recovery;
      saveDatasetImportRecovery(projectId, recovery);
      setImportRecovery(recovery);
      const imported = await apiClient.importDatasetSamples(projectId, datasetId, importSamples);
      setImportProgress({ datasetId, created: true, imported: true });
      clearDatasetImportRecovery(projectId);
      setImportRecovery(null);
      setLocalDatasets((current) => [{ ...imported.dataset, mockOnly: apiMode === 'mock' }, ...(current ?? [])]);
      setFeedback(`已导入 ${importSamples.length} 条本地 JSONL 样本；数据集仍为草稿，请单独发布。`);
      setDialog(null);
    } catch (error) {
      const recovery = recoveryForAttempt;
      if (recovery?.created) {
        try {
          const saved = await apiClient.listDatasetSamples(projectId, recovery.datasetId);
          if (sameImportContent(importSamples, saved)) {
            const dataset = await apiClient.getDataset(projectId, recovery.datasetId);
            clearDatasetImportRecovery(projectId);
            setImportRecovery(null);
            setImportProgress({ datasetId: recovery.datasetId, created: true, imported: true });
            setLocalDatasets((current) => [{ ...dataset, mockOnly: apiMode === 'mock' }, ...(current ?? []).filter((item) => item.id !== dataset.id)]);
            setFeedback('导入响应未返回，但已只读核对样本；数据集仍为草稿。');
            setDialog(null);
            return;
          }
          setImportError(saved.length ? '该草稿已有不同样本，请先核对后再处理；没有追加或覆盖数据。' : (error instanceof Error ? error.message : '导入失败，草稿已保留，可重试。'));
        } catch { setImportError(error instanceof Error ? error.message : '导入失败，草稿已保留，可重试。'); }
      } else setImportError(error instanceof Error ? error.message : '导入失败。');
    } finally { setSaving(false); }
  };

  const publishDataset = async (dataset: DisplayDataset) => {
    if (dataset.sampleCount === 0 || publishingId) return;
    setPublishingId(dataset.id);
    try {
      const published = await apiClient.publishDataset(projectId, dataset.id);
      setLocalDatasets((current) => (current ?? datasets).map((item) => item.id === dataset.id
        ? { ...published, mockOnly: item.mockOnly }
        : item));
      setDialog(null);
      setFeedback(apiMode === 'mock'
        ? `Mock 数据集“${dataset.name}”已发布（仅当前会话）`
        : `数据集“${dataset.name}”已通过 API 发布并冻结`);
    } catch (error) {
      setFeedback(error instanceof Error ? `发布失败：${error.message}` : '发布失败，请稍后重试');
    } finally {
      setPublishingId(null);
    }
  };

  const createDataset = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const created = await apiClient.createDataset(projectId, {
        name: draft.name.trim(),
        description: draft.description.trim() || undefined,
        owner: draft.owner.trim() || '当前用户',
        version: 'v0.1',
      });
      setLocalDatasets((current) => [{ ...created, mockOnly: apiMode === 'mock' }, ...(current ?? [])]);
      setDraft({ name: '', description: '', owner: '当前用户' });
      setDialog(null);
      setFeedback(apiMode === 'mock'
        ? `已在前端状态中新建 Mock 数据集“${created.name}”`
        : `已通过 API 新建数据集草稿“${created.name}”`);
    } catch (error) {
      setFeedback(error instanceof Error ? `创建失败：${error.message}` : '创建失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  const showDetails = (datasetId: string) => {
    setSelectedDatasetId(datasetId);
    setOpenMenuId(null);
    setDialog('details');
  };

  const copyDatasetId = async (dataset: DisplayDataset) => {
    setOpenMenuId(null);
    try {
      await copyText(dataset.id);
      setFeedback(`已复制数据集 ID：${dataset.id}`);
    } catch {
      setFeedback(`复制失败，请手动复制：${dataset.id}`);
    }
  };

  const toggleArchived = (dataset: DisplayDataset) => {
    if (!ensureMockArchive()) return;
    setOpenMenuId(null);
    setLocalDatasets((current) => (current ?? datasets).map((item) => item.id === dataset.id ? { ...item, archived: !item.archived } : item));
    setFeedback(dataset.archived ? `已恢复 Mock 数据集“${dataset.name}”` : `已将“${dataset.name}”标记为归档（Mock）`);
  };

  const openImport = () => {
    const recovery = loadDatasetImportRecovery(projectId);
    if (recovery && !recovery.imported) {
      setImportRecovery(recovery); setImportProgress({ datasetId: recovery.datasetId, created: true, imported: false });
      setImportSamples(recovery.samples); setImportName(recovery.name); setImportFileName(recovery.fileName);
    } else { setImportSamples(null); setImportError(null); setImportProgress(null); setImportName(''); setImportFileName('local.jsonl'); }
    setDialog('import');
  };

  return (
    <>
      <PageIntro
        title="数据集管理"
        description="管理黄金问答集与边界样本；版本、覆盖率和最近评测均可追溯。"
        actions={<><button className="button button-secondary" type="button" onClick={openImport}><Upload size={15} />导入数据</button><button className="button button-primary" type="button" onClick={() => setDialog('create')}><FilePlus2 size={15} />新建数据集</button></>}
      />
      <PartialDataBanner message={state.partialMessage} />
      <Panel
        title={`数据集（${datasets.length}）`}
        eyebrow="PROJECT ASSETS"
        action={(
          <div className="toolbar">
            <label className="search-box"><Search size={15} /><input aria-label="搜索数据集" placeholder="搜索名称" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
            <button className="button button-quiet" type="button" onClick={() => void refreshDatasets()} disabled={refreshing} aria-busy={refreshing}>
              <RefreshCw className={refreshing ? 'icon-spin' : undefined} size={15} />{refreshing ? '刷新中' : '刷新数据集'}
            </button>
            <div className="menu-anchor">
              <button className={`button button-quiet ${statusFilter !== 'all' ? 'filter-active' : ''}`} type="button" aria-expanded={filterOpen} onClick={() => setFilterOpen((value) => !value)}><Filter size={15} />筛选{statusFilter !== 'all' && ' · 1'}</button>
              {filterOpen && <div className="filter-popover"><label>数据集状态<select aria-label="按状态筛选数据集" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as DatasetFilter)}>{statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label><button type="button" onClick={() => { setStatusFilter('all'); setFilterOpen(false); }}>清除筛选</button></div>}
            </div>
          </div>
        )}
      >
        {refreshing && <div className="refresh-progress" role="status" aria-live="polite">正在刷新数据集，当前列表与筛选保持可用。</div>}
        {refreshError && <RefreshErrorBanner subject="数据集" message={refreshError} onRetry={() => void refreshDatasets()} retrying={refreshing} />}
        {datasets.length === 0 ? (
          <EmptyState title="还没有数据集" description="导入 CSV / JSONL，或创建一个空数据集开始维护评测样本。" action={<button className="button button-primary" type="button" onClick={openImport}><Upload size={15} />导入首个数据集</button>} />
        ) : filtered.length === 0 ? (
          <EmptyState title="未找到匹配数据集" description="尝试更换关键词或清空搜索、状态筛选条件。" />
        ) : (
          <div className="table-wrap" tabIndex={0} role="region" aria-label="数据集表格，可横向滚动查看完整字段与操作">
            <table>
              <thead><tr><th>数据集</th><th>状态</th><th>版本</th><th>样本量</th><th>场景覆盖</th><th>负责人</th><th>更新时间</th><th /></tr></thead>
              <tbody>{filtered.map((dataset) => (
                <tr key={dataset.id} className={dataset.archived ? 'row-archived' : ''}>
                  <td className="dataset-name"><span className="dataset-icon">DS</span><span><strong>{dataset.name} {dataset.mockOnly && <em className="mock-label">MOCK</em>} {dataset.archived && <em className="archive-label">已归档</em>}</strong><small>{dataset.description}</small></span></td>
                  <td><StatusBadge value={dataset.status} /></td>
                  <td><code>{dataset.version}</code></td>
                  <td>{dataset.sampleCount}</td>
                  <td>{dataset.coverage === null ? <span className="unknown-value">未知</span> : <div className="coverage"><span><i style={{ width: `${dataset.coverage}%` }} /></span><strong>{dataset.coverage}%</strong></div>}</td>
                  <td>{dataset.owner}</td>
                  <td>{formatDateTime(dataset.updatedAt)}</td>
                  <td>
                    <div className="menu-anchor row-menu-anchor">
                      <button className="icon-button" type="button" aria-label={`${dataset.name} 更多操作`} aria-expanded={openMenuId === dataset.id} onClick={() => setOpenMenuId((current) => current === dataset.id ? null : dataset.id)}><MoreHorizontal size={17} /></button>
                      {openMenuId === dataset.id && <div className="action-menu" role="menu"><button type="button" role="menuitem" onClick={() => showDetails(dataset.id)}><Eye size={14} />查看详情</button><button type="button" role="menuitem" onClick={() => void copyDatasetId(dataset)}><Copy size={14} />复制 ID</button><button type="button" role="menuitem" onClick={() => toggleArchived(dataset)}><Archive size={14} />{dataset.archived ? '恢复数据集' : '标记归档'}</button></div>}
                    </div>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>

      <Dialog
        open={false}
        title="导入示例 JSONL"
        eyebrow={apiMode === 'mock' ? 'MOCK IMPORT' : 'API IMPORT'}
        onClose={() => setDialog(null)}
        footer={<><button className="button button-secondary" type="button" onClick={() => setDialog(null)}>取消</button><button className="button button-primary" type="button" onClick={() => void importExample()} disabled={saving}><Upload size={15} />导入示例 JSONL</button></>}
      >
        <p>演示文件包含 12 条人工构造样本，使用 2.0 契约分开问题、参考标签、给定上下文和历史输出。</p>
        <pre className="jsonl-preview">{`{"schema_version":"2.0","sample_id":"refund-example-01","question":"退款后成长值如何处理？","labels":{"reference_answer":"按退款金额比例扣回。","gold_document_ids":["doc-refund-policy-01"]},"contexts":[{"origin":"provided","rank":1,"retrieval_run_id":null,"doc_id":"doc-refund-policy-01","chunk_id":"chunk-refund-policy-01","text":"退款成功后，成长值按退款商品实付金额比例扣回。","score":null}]}`}</pre>
        <p className="form-hint">{apiMode === 'mock' ? '将在内存中依次创建、导入和发布，并明确标记为 MOCK。' : '将依次调用创建、样本导入和发布接口；任一步失败都会显示后端错误，不会改用 fixture。'}</p>
      </Dialog>

      <Dialog
        open={dialog === 'import'}
        title="导入本地 JSONL"
        eyebrow="PREVIEW BEFORE WRITE"
        onClose={() => setDialog(null)}
        footer={<><button className="button button-secondary" type="button" onClick={() => setDialog(null)}>取消</button><button className="button button-secondary" type="button" onClick={() => void importExample()} disabled={saving}>导入演示数据</button><button data-testid="confirm-local-jsonl-import" className="button button-primary" type="button" onClick={() => void importLocalFile()} disabled={saving || !importSamples}>{saving ? '导入中' : '确认创建草稿并导入'}</button></>}
      >
        <input data-testid="local-jsonl-input" ref={fileInput} type="file" accept=".jsonl,application/jsonl,application/x-ndjson" hidden onChange={(event) => void receiveJsonl(event.target.files?.[0])} />
        <button className="file-drop-zone" type="button" onClick={() => fileInput.current?.click()} onDragOver={(event: DragEvent<HTMLButtonElement>) => event.preventDefault()} onDrop={(event: DragEvent<HTMLButtonElement>) => { event.preventDefault(); void receiveJsonl(event.dataTransfer.files[0]); }}>
          拖放 JSONL 文件到这里，或点击选择文件（UTF-8，支持 BOM / LF / CRLF）
        </button>
        {importRecovery && <p className="form-hint" role="status">检测到未完成导入：{importRecovery.fileName}（草稿 {importRecovery.datasetId}）。可继续原操作；不会自动发布。</p>}
        {pendingImport && <div className="verification-confirm" role="alert"><p>新文件与未完成草稿不同。请选择继续原导入，或明确放弃原草稿后以新文件开始；不会静默写入原草稿。</p><button className="button button-secondary" type="button" onClick={() => setPendingImport(null)}>继续原操作</button><button className="button button-secondary" type="button" onClick={() => { clearDatasetImportRecovery(projectId); applyParsedImport(pendingImport.samples, pendingImport.name, pendingImport.fileName); }}>放弃原操作并使用新文件</button></div>}
        {importError && <p className="form-hint" role="alert">{importError}</p>}
        {importSamples && <><label>数据集名称<input aria-label="导入数据集名称" value={importName} onChange={(event) => setImportName(event.target.value)} /></label><p className="form-hint">预检通过：共 {importSamples.length} 条；示例：{importSamples.slice(0, 3).map((item) => item.question).join('；')}。确认前不会发起写入请求。</p></>}
        {importProgress && !importProgress.imported && <p className="form-hint">创建已完成（{importProgress.datasetId}），样本导入未完成；可直接重试，不会重复创建数据集。</p>}
      </Dialog>

      <Dialog
        open={dialog === 'create'}
        title="新建数据集"
        eyebrow={apiMode === 'mock' ? 'LOCAL DRAFT' : 'API DRAFT'}
        onClose={() => setDialog(null)}
        footer={<><button className="button button-secondary" type="button" onClick={() => setDialog(null)}>取消</button><button className="button button-primary" type="submit" form="create-dataset-form" disabled={saving}><FilePlus2 size={15} />{apiMode === 'mock' ? '创建 Mock 数据集' : '创建数据集草稿'}</button></>}
      >
        <form className="form-grid" id="create-dataset-form" onSubmit={createDataset}>
          <label>名称<input required aria-label="数据集名称" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} placeholder="例如：售后边界样本" /></label>
          <label>负责人<input aria-label="数据集负责人" value={draft.owner} onChange={(event) => setDraft((current) => ({ ...current, owner: event.target.value }))} /></label>
          <label className="field-full">描述<textarea aria-label="数据集描述" value={draft.description} onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))} placeholder="说明覆盖场景与维护目标" /></label>
        </form>
        <p className="form-hint">{apiMode === 'mock' ? '将创建一个样本量为 0 的 Mock 草稿，不会写入真实服务。' : '将调用 POST /datasets 创建服务端草稿；发布仍由后端发布接口完成。'}</p>
      </Dialog>

      <Dialog
        open={dialog === 'details' && Boolean(selectedDataset)}
        title={selectedDataset?.name ?? '数据集详情'}
        eyebrow="DATASET DETAIL"
        onClose={() => setDialog(null)}
        footer={selectedDataset?.status === 'draft' ? <button className="button button-primary" type="button" disabled={selectedDataset.sampleCount === 0 || publishingId === selectedDataset.id} onClick={() => void publishDataset(selectedDataset)}>{publishingId === selectedDataset.id ? '发布中' : '发布并冻结数据集'}</button> : undefined}
      >
        {selectedDataset && <><dl className="detail-list"><div><dt>ID</dt><dd><code>{selectedDataset.id}</code></dd></div><div><dt>状态</dt><dd><StatusBadge value={selectedDataset.status} /> {selectedDataset.archived && <span className="archive-label">已归档</span>}</dd></div><div><dt>样本 / 覆盖</dt><dd>{selectedDataset.sampleCount} 条 · {selectedDataset.coverage === null ? '覆盖未知' : `${selectedDataset.coverage}%`}</dd></div><div><dt>Schema / 版本</dt><dd><code>{selectedDataset.schemaVersion}</code> · {selectedDataset.version}</dd></div><div><dt>内容哈希</dt><dd>{selectedDataset.contentSha256 ? <code>{selectedDataset.contentSha256}</code> : '发布前未知'}</dd></div><div><dt>负责人</dt><dd>{selectedDataset.owner}</dd></div><div><dt>更新时间</dt><dd>{formatDateTime(selectedDataset.updatedAt)}</dd></div></dl>{selectedDataset.status === 'draft' && selectedDataset.sampleCount === 0 && <p className="form-hint">发布前至少需要一条有效样本；空草稿不会发送发布请求。</p>}</>}
      </Dialog>
      <Toast message={feedback} onDismiss={() => setFeedback(null)} />
    </>
  );
}
