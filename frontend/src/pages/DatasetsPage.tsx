import { FilePlus2, Filter, MoreHorizontal, Search, Upload } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useOutletContext, useParams } from 'react-router-dom';
import { apiClient } from '../api/client';
import { PageIntro, Panel } from '../components/Panel';
import { EmptyState, ErrorState, LoadingState, PartialDataBanner } from '../components/PageState';
import { StatusBadge } from '../components/StatusBadge';
import type { WorkspaceOutletContext } from '../components/WorkspaceShell';
import { useApiResource } from '../hooks/useApiResource';
import { formatDateTime } from '../lib/format';

export function DatasetsPage() {
  const { projectId = 'demo' } = useParams();
  const { scenario } = useOutletContext<WorkspaceOutletContext>();
  const [query, setQuery] = useState('');
  const { state, retry } = useApiResource(
    () => apiClient.listDatasets(projectId),
    [projectId],
    { scenario, emptyValue: [], partialize: (data) => data.slice(0, 2) },
  );
  const filtered = useMemo(() => state.status === 'success'
    ? state.data.filter((dataset) => dataset.name.toLowerCase().includes(query.toLowerCase()))
    : [], [query, state]);

  if (state.status === 'loading') return <LoadingState label="正在载入数据集" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;

  return (
    <>
      <PageIntro
        title="数据集管理"
        description="管理黄金问答集与边界样本；版本、覆盖率和最近评测均可追溯。"
        actions={<><button className="button button-secondary" type="button"><Upload size={15} />导入数据</button><button className="button button-primary" type="button"><FilePlus2 size={15} />新建数据集</button></>}
      />
      <PartialDataBanner message={state.partialMessage} />
      <Panel title={`数据集（${state.data.length}）`} eyebrow="PROJECT ASSETS" action={<div className="toolbar"><label className="search-box"><Search size={15} /><input aria-label="搜索数据集" placeholder="搜索名称" value={query} onChange={(event) => setQuery(event.target.value)} /></label><button className="button button-quiet" type="button"><Filter size={15} />筛选</button></div>}>
        {state.data.length === 0 ? (
          <EmptyState title="还没有数据集" description="导入 CSV / JSONL，或创建一个空数据集开始维护评测样本。" action={<button className="button button-primary" type="button"><Upload size={15} />导入首个数据集</button>} />
        ) : filtered.length === 0 ? (
          <EmptyState title="未找到匹配数据集" description="尝试更换关键词或清空搜索条件。" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>数据集</th><th>状态</th><th>版本</th><th>样本量</th><th>场景覆盖</th><th>负责人</th><th>更新时间</th><th /></tr></thead>
              <tbody>{filtered.map((dataset) => (
                <tr key={dataset.id}>
                  <td className="dataset-name"><span className="dataset-icon">DS</span><span><strong>{dataset.name}</strong><small>{dataset.description}</small></span></td>
                  <td><StatusBadge value={dataset.status} /></td>
                  <td><code>{dataset.version}</code></td>
                  <td>{dataset.sampleCount}</td>
                  <td><div className="coverage"><span><i style={{ width: `${dataset.coverage}%` }} /></span><strong>{dataset.coverage}%</strong></div></td>
                  <td>{dataset.owner}</td>
                  <td>{formatDateTime(dataset.updatedAt)}</td>
                  <td><button className="icon-button" type="button" aria-label={`${dataset.name} 更多操作`}><MoreHorizontal size={17} /></button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
