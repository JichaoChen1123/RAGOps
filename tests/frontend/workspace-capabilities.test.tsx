import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../../frontend/src/App';
import { apiClient } from '../../frontend/src/api/client';
import { MetricCard } from '../../frontend/src/components/MetricCard';

function renderOverview() {
  return render(
    <MemoryRouter initialEntries={['/projects/demo/overview']}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function renderEvaluations() {
  return render(
    <MemoryRouter initialEntries={['/projects/demo/evaluations']}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('workspace navigation and RAGOps capabilities', () => {
  it('keeps recent tasks visible when there are no evaluated quality metrics', async () => {
    const overview = await apiClient.getProjectOverview('demo');
    const spy = vi.spyOn(apiClient, 'getProjectOverview').mockResolvedValue({
      ...overview, metrics: [], trend: [],
    });
    try {
      renderOverview();
      await screen.findByText('暂无已评质量指标');
      expect(screen.getByText('最近评测任务')).toBeInTheDocument();
      expect(screen.getByRole('link', { name: `查看 ${overview.recentTasks[0].name} 报告` })).toBeInTheDocument();
    } finally {
      spy.mockRestore();
    }
  });

  it('distinguishes active, available, coming-soon and disabled navigation entries', async () => {
    const user = userEvent.setup();
    renderOverview();
    await screen.findByRole('heading', { level: 2, name: '客服 RAG 生产线' });

    expect(screen.getByRole('link', { name: '项目概览' })).toHaveClass('active');
    expect(screen.getByRole('link', { name: '趋势看板，从概览查看' })).toHaveTextContent('LIVE');

    const comingSoon = screen.getByRole('button', { name: '版本对比，即将推出' });
    expect(comingSoon).toHaveTextContent('NEXT');
    await user.click(comingSoon);
    const roadmap = screen.getByRole('dialog', { name: '版本对比 · 下一阶段' });
    expect(within(roadmap).getByText(/选择基线任务|基线任务/)).toBeInTheDocument();
    expect(within(roadmap).getByText('指标回归')).toBeInTheDocument();

    const projectSettings = screen.getByRole('button', { name: '项目设置，连接 API 后开放' });
    expect(projectSettings).toBeDisabled();
    expect(projectSettings).toHaveTextContent('连接 API 后开放');
  });

  it('shows the complete evaluation pipeline and engineering capability matrix', async () => {
    renderOverview();
    const pipeline = await screen.findByRole('region', { name: 'RAGOps 技术链路' });

    for (const step of ['Dataset', 'Evaluation Job', 'Metrics', 'Failure Diagnosis', 'Report', 'Review']) {
      expect(within(pipeline).getByText(step)).toBeInTheDocument();
    }
    expect(within(pipeline).getByText('多维质量评测')).toBeInTheDocument();
    expect(within(pipeline).getByText('证据级故障归因')).toBeInTheDocument();
    expect(within(pipeline).getByText('运行版本可追溯')).toBeInTheDocument();
    expect(within(pipeline).getByText('工程质量门禁')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '当前评测运行上下文' })).toHaveTextContent('MOCK FIXTURE');
  });

  it('opens the read-only three-axis runtime status from the sidebar', async () => {
    const user = userEvent.setup();
    renderOverview();
    await screen.findByRole('heading', { level: 2, name: '客服 RAG 生产线' });

    await user.click(screen.getByRole('button', { name: '模型与 Prompt，只读快照' }));
    const snapshot = screen.getByRole('dialog', { name: '模型与 Prompt · 只读快照' });
    expect(snapshot).toHaveTextContent('Mock fixture（浏览器内存）');
    expect(snapshot).toHaveTextContent('BACKEND EXECUTION ADAPTER');
    expect(snapshot).toHaveTextContent('mock');
    expect(snapshot).toHaveTextContent('openai_compatible · 未配置');
    expect(snapshot).toHaveTextContent('真实验证必须在评测任务页由用户主动发起');
  });

  it('offers three independent model channels and keeps real checks explicit', async () => {
    const user = userEvent.setup();
    renderEvaluations();
    await screen.findByRole('heading', { level: 2, name: '评测任务' });
    await user.click(screen.getByRole('button', { name: '新建评测任务' }));
    const dialog = screen.getByRole('dialog', { name: '新建评测任务' });
    const channel = within(dialog).getByRole('combobox', { name: '选择后端执行器' });

    expect(within(channel).getByRole('option', { name: /mock/ })).toBeInTheDocument();
    expect(within(channel).getByRole('option', { name: /codex_chatgpt/ })).toBeInTheDocument();
    expect(within(channel).getByRole('option', { name: /openai_compatible/ })).toBeInTheDocument();

    await user.selectOptions(channel, 'codex_chatgpt');
    expect(within(dialog).getByRole('button', { name: '检查登录' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: '真实小请求验证' })).toBeDisabled();
    expect(dialog).toHaveTextContent('前端 Mock 数据模式不会连接真实模型通道');
  });

  it('labels partial metric coverage instead of presenting it as an all-sample result', () => {
    render(<MetricCard metric={{ key: 'support', label: '引用支持率', value: 1, status: 'ok', evaluatedCount: 1, excludedCount: 2 }} />);
    expect(screen.getByRole('article')).toHaveTextContent('已评 1 / 3 个样本（非整批）');
  });

  it('shows sample-level channel, model identity, usage and request ID in reports', async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={['/projects/demo/evaluations/eval-20260826/report']}><AppRoutes /></MemoryRouter>);
    await screen.findByRole('heading', { level: 2, name: /客服知识库 v3 回归评测/ });
    expect(screen.getByText('0 / 3（部分样本）')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '表格列表' }));
    const table = screen.getByRole('table');
    expect(table).toHaveTextContent('mock-ragops-v1 → mock-ragops-v1');
    expect(table).toHaveTextContent('usage 未知 · 成本未知');
    expect(table).toHaveTextContent('request ID：未知');
    expect(table).toHaveTextContent('SIMULATED');
  });
});
