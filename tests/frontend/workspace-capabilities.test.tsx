import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../../frontend/src/App';
import { apiClient } from '../../frontend/src/api/client';

function renderOverview() {
  return render(
    <MemoryRouter initialEntries={['/projects/demo/overview']}>
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
    expect(snapshot).toHaveTextContent('本阶段不提供真实验证入口');
  });
});
