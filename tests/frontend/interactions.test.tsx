import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../../frontend/src/App';
import { apiClient } from '../../frontend/src/api/client';
import { datasets, evaluationTasks } from '../../frontend/src/api/fixtures';
import type { Dataset, EvaluationTask } from '../../frontend/src/types';

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('RAGOps MVP interaction loops', () => {
  it('imports the example JSONL from the dataset empty state', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/datasets?state=empty');

    await user.click(await screen.findByRole('button', { name: /导入首个数据集/ }));
    const dialog = screen.getByRole('dialog', { name: '导入示例 JSONL' });
    expect(within(dialog).getByText(/12 条退款政策问答/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: /^导入示例 JSONL$/ }));

    expect(await screen.findByText('退款政策示例 JSONL')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Mock 示例 JSONL 导入完成');
  });

  it('creates, filters and archives a local dataset', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/datasets');
    await screen.findByRole('heading', { level: 2, name: '数据集管理' });

    await user.click(screen.getByRole('button', { name: /新建数据集/ }));
    await user.type(screen.getByRole('textbox', { name: '数据集名称' }), '售后边界样本');
    await user.click(screen.getByRole('button', { name: /创建 Mock 数据集/ }));
    expect(await screen.findByText('售后边界样本')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '筛选' }));
    await user.selectOptions(screen.getByRole('combobox', { name: '按状态筛选数据集' }), 'draft');
    expect(screen.getByText('售后边界样本')).toBeInTheDocument();
    expect(screen.queryByText('账单边界样本')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '售后边界样本 更多操作' }));
    await user.click(screen.getByRole('menuitem', { name: /标记归档/ }));
    expect(await screen.findByText('已归档')).toBeInTheDocument();
  });

  it('searches datasets and makes details and copy actions observable', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    renderRoute('/projects/demo/datasets');
    await screen.findByText('客服黄金问答集');

    await user.type(screen.getByRole('textbox', { name: '搜索数据集' }), '账单');
    expect(screen.getByText('账单边界样本')).toBeInTheDocument();
    expect(screen.queryByText('客服黄金问答集')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '账单边界样本 更多操作' }));
    await user.click(screen.getByRole('menuitem', { name: '查看详情' }));
    const details = screen.getByRole('dialog', { name: '账单边界样本' });
    expect(within(details).getByText('ds-billing-edge')).toBeInTheDocument();
    expect(within(details).getByText(/64 条/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '关闭账单边界样本' }));

    await user.click(screen.getByRole('button', { name: '账单边界样本 更多操作' }));
    await user.click(screen.getByRole('menuitem', { name: '复制 ID' }));
    expect(writeText).toHaveBeenCalledWith('ds-billing-edge');
    expect(await screen.findByRole('status')).toHaveTextContent('已复制数据集 ID：ds-billing-edge');
  });

  it('refreshes datasets without hiding stale data and offers a retry after failure', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/datasets');
    await screen.findByText('客服黄金问答集');

    const failedRefresh = deferred<Dataset[]>();
    const refreshedDatasets: Dataset[] = [
      { ...datasets[0], id: 'ds-refreshed', name: '刷新后的数据集' },
      ...datasets,
    ];
    const listSpy = vi.spyOn(apiClient, 'listDatasets')
      .mockReturnValueOnce(failedRefresh.promise)
      .mockResolvedValueOnce(refreshedDatasets);

    const refreshButton = screen.getByRole('button', { name: '刷新数据集' });
    await user.click(refreshButton);

    expect(refreshButton).toBeDisabled();
    expect(refreshButton).toHaveTextContent('刷新中');
    expect(screen.getByText('客服黄金问答集')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('当前列表与筛选保持可用');

    failedRefresh.reject(new Error('数据集服务暂时不可用'));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('数据集刷新失败');
    expect(alert).toHaveTextContent('当前仍显示上次成功加载的数据');
    expect(screen.getByText('客服黄金问答集')).toBeInTheDocument();

    await user.click(within(alert).getByRole('button', { name: '重试刷新' }));
    expect(await screen.findByText('刷新后的数据集')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Mock 数据集列表已刷新');
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(listSpy).toHaveBeenCalledTimes(2);
  });

  it('creates a running mock evaluation and filters by status', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/evaluations?state=empty');

    await user.click(await screen.findByRole('button', { name: /新建首个任务/ }));
    await user.selectOptions(screen.getByRole('combobox', { name: '选择任务状态' }), 'running');
    await user.click(screen.getByRole('button', { name: /生成 Mock 任务/ }));
    expect(await screen.findByText(/Mock 评测/)).toBeInTheDocument();
    expect(screen.getByText('运行中')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '筛选' }));
    await user.selectOptions(screen.getByRole('combobox', { name: '按状态筛选评测任务' }), 'completed');
    expect(await screen.findByText('未找到匹配任务')).toBeInTheDocument();
  });

  it('searches evaluation tasks and opens the matching completed report', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/evaluations');
    await screen.findByText('客服知识库 v3 回归评测');

    await user.type(screen.getByRole('textbox', { name: '搜索评测任务' }), '客服知识库');
    expect(screen.getByText('客服知识库 v3 回归评测')).toBeInTheDocument();
    expect(screen.queryByText('Rerank 参数 A/B 基线')).not.toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: /查看报告/ }));

    expect(await screen.findByRole('heading', { level: 2, name: '客服知识库 v3 回归评测' })).toBeInTheDocument();
    expect(screen.getByText('发布门禁结论')).toBeInTheDocument();
  });

  it('refreshes task status while preserving the table and retries a failed read', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/evaluations');
    await screen.findByText('Rerank 参数 A/B 基线');

    const failedRefresh = deferred<EvaluationTask[]>();
    const refreshedTasks: EvaluationTask[] = evaluationTasks.map((task) => task.id === 'eval-20260825'
      ? { ...task, status: 'completed', progress: 100, completedAt: '2026-08-27T13:00:00+08:00', score: 90.2 }
      : task);
    const listSpy = vi.spyOn(apiClient, 'listEvaluationTasks')
      .mockReturnValueOnce(failedRefresh.promise)
      .mockResolvedValueOnce(refreshedTasks);

    const refreshButton = screen.getByRole('button', { name: '刷新任务状态' });
    await user.click(refreshButton);

    expect(refreshButton).toBeDisabled();
    expect(screen.getByText('Rerank 参数 A/B 基线')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('当前列表与筛选保持可用');

    failedRefresh.reject(new Error('任务状态读取超时'));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('任务状态刷新失败');
    expect(alert).toHaveTextContent('当前仍显示上次成功加载的数据');
    expect(screen.getByText('Rerank 参数 A/B 基线')).toBeInTheDocument();

    await user.click(within(alert).getByRole('button', { name: '重试刷新' }));
    const refreshedRow = (await screen.findByText('Rerank 参数 A/B 基线')).closest('tr');
    expect(refreshedRow).not.toBeNull();
    expect(within(refreshedRow!).getByText('已完成')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Mock 任务状态已刷新');
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(listSpy).toHaveBeenCalledTimes(2);
  });

  it('opens trend details and reports refresh feedback', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/overview');
    await screen.findByRole('heading', { level: 2, name: '客服 RAG 生产线' });

    await user.click(screen.getByRole('button', { name: /查看趋势看板/ }));
    expect(screen.getByRole('dialog', { name: '质量与延迟趋势' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '关闭质量与延迟趋势' }));
    await user.click(screen.getByRole('button', { name: /刷新数据/ }));

    expect(await screen.findByText('正在重新载入 Mock 项目数据')).toBeInTheDocument();
  });

  it('uses the overview new-evaluation entry to open the creation dialog', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/overview');
    await screen.findByRole('heading', { level: 2, name: '客服 RAG 生产线' });

    await user.click(screen.getByRole('link', { name: '新建评测' }));
    expect(await screen.findByRole('heading', { level: 2, name: '评测任务' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '新建评测任务' }));
    expect(screen.getByRole('dialog', { name: '新建评测任务' })).toBeInTheDocument();
  });

  it('filters report samples, compares versions and exports JSON', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/evaluations/eval-20260826/report');
    await screen.findByText('发布门禁结论');

    await user.click(screen.getByRole('button', { name: '已确认 1' }));
    expect(screen.getByText('sample-017')).toBeInTheDocument();
    expect(screen.queryByText('sample-042')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /对比版本/ }));
    expect(screen.getByRole('dialog', { name: '版本对比' })).toHaveTextContent('CURRENT VS BASELINE');
    await user.click(screen.getByRole('button', { name: '关闭版本对比' }));
    await user.click(screen.getByRole('button', { name: /导出报告/ }));
    await user.click(within(screen.getByRole('dialog', { name: '导出评测报告' })).getByRole('button', { name: /JSON/ }));
    expect(await screen.findByText('已导出 JSON 报告')).toBeInTheDocument();
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  it('copies an answer, opens source details and confirms diagnosis', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    renderRoute('/projects/demo/evaluations/eval-20260826/samples/sample-042');
    await screen.findByText('关键政策文档未进入 Top 5');

    await user.click(screen.getByRole('button', { name: '复制模型回答' }));
    expect(writeText).toHaveBeenCalled();
    expect(await screen.findByText('已复制模型回答')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /打开源文档/ }));
    expect(screen.getByRole('dialog', { name: /会员成长值常见问题/ })).toHaveTextContent('kb://membership/archive/faq-2024');
    await user.click(screen.getByRole('button', { name: /关闭会员成长值常见问题/ }));
    await user.click(screen.getByRole('button', { name: /确认故障归因/ }));
    expect(await screen.findByText('故障归因已在当前页面确认')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /确认故障归因/ })).toBeDisabled();
  });

  it('links a citation to its evidence and dismisses the diagnosis', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/evaluations/eval-20260826/samples/sample-042');
    await screen.findByText('关键政策文档未进入 Top 5');

    await user.click(screen.getByRole('button', { name: /\[2\].*不支持/ }));
    expect(screen.getByRole('heading', { level: 3, name: '订单退款通用规则' })).toBeInTheDocument();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '排除诊断' }));
    expect(await screen.findByRole('status')).toHaveTextContent('已排除本次诊断（仅当前页面会话）');
    expect(screen.getByRole('button', { name: '排除诊断' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '排除诊断' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('makes workspace search, help and sidebar controls actionable', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/overview');
    await screen.findByRole('heading', { level: 2, name: '客服 RAG 生产线' });

    await user.click(screen.getByRole('button', { name: '使用帮助' }));
    expect(screen.getByRole('dialog', { name: 'RAGOps 快速帮助' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '关闭RAGOps 快速帮助' }));

    await user.click(screen.getByRole('button', { name: '搜索' }));
    await user.type(screen.getByRole('textbox', { name: '搜索页面' }), '数据集');
    await user.click(screen.getByRole('link', { name: /数据集管理/ }));
    expect(await screen.findByRole('heading', { level: 2, name: '数据集管理' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '收起侧边栏' }));
    expect(screen.getByRole('button', { name: '展开侧边栏' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: /客服 RAG 生产线/ }));
    const projectMenu = screen.getByRole('menu');
    expect(within(projectMenu).getByRole('menuitem', { name: /其他项目/ })).toBeDisabled();
    await user.click(within(projectMenu).getByRole('menuitem', { name: /客服 RAG 生产线/ }));
    expect(await screen.findByRole('status')).toHaveTextContent('当前已是“客服 RAG 生产线”');
  });
});
