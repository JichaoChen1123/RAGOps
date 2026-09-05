import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../../frontend/src/App';
import { apiClient } from '../../frontend/src/api/client';
import { TaskStack } from '../../frontend/src/components/TaskStack';
import { evaluationTasks } from '../../frontend/src/api/fixtures';

function route(path = '/projects/demo/overview') {
  return render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>);
}

describe('redesigned workbench contracts', () => {
  it('keeps execution success separate from unknown quality in a run card', () => {
    render(<MemoryRouter><TaskStack projectId="demo" tasks={[{ ...evaluationTasks[0], status: 'completed', outcome: 'succeeded', qualityStatus: 'not_evaluated', qualityVerdict: 'unknown', qualityScore: null, isMock: true }]} /></MemoryRouter>);
    const record = screen.getByRole('article');
    expect(record).toHaveTextContent('执行成功');
    expect(record).toHaveTextContent('未评估');
    expect(record).toHaveTextContent('质量分未知');
    expect(record).toHaveTextContent('SIMULATED');
    expect(record).not.toHaveTextContent('100');
  });

  it('provides a mobile navigation disclosure, Escape and close on route change', async () => {
    const user = userEvent.setup();
    route();
    await screen.findByText('最近评测任务');
    await user.click(screen.getByRole('button', { name: '打开主导航' }));
    expect(screen.getByRole('button', { name: '关闭主导航' })).toHaveAttribute('aria-expanded', 'true');
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: '打开主导航' })).toHaveFocus();
    await user.click(screen.getByRole('button', { name: '打开主导航' }));
    await user.click(screen.getByRole('link', { name: '数据集' }));
    await screen.findByRole('heading', { level: 2, name: '数据集管理' });
    expect(screen.getByRole('button', { name: '打开主导航' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('traps dialog focus, accepts Escape, restores the trigger and body scroll', async () => {
    const user = userEvent.setup();
    route('/projects/demo/datasets');
    const trigger = await screen.findByRole('button', { name: '新建数据集' });
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: '新建数据集' });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    expect(document.body.style.overflow).toBe('hidden');
    const first = within(dialog).getByRole('button', { name: '关闭新建数据集' });
    const last = within(dialog).getByRole('button', { name: '创建 Mock 数据集' });
    last.focus();
    await user.tab();
    expect(first).toHaveFocus();
    await user.tab({ shift: true });
    expect(last).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('preserves filters across sample card and table views', async () => {
    const user = userEvent.setup();
    route('/projects/demo/evaluations/eval-20260826/report');
    await screen.findByRole('region', { name: '样本诊断卡片' });
    await user.click(screen.getByRole('button', { name: '样本诊断卡片：下一项' }));
    expect(screen.getByRole('article', { name: 'sample-017' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '已确认 1' }));
    await user.click(screen.getByRole('button', { name: '表格列表' }));
    const table = screen.getByRole('table');
    expect(table).toHaveTextContent('sample-017');
    expect(table).not.toHaveTextContent('sample-042');
    await user.click(screen.getByRole('button', { name: '卡片浏览' }));
    expect(within(screen.getByRole('region', { name: '样本诊断卡片' })).getByRole('article')).toHaveAccessibleName('sample-017');
    await user.click(screen.getByRole('button', { name: /^全部 / }));
    expect(screen.getByRole('region', { name: '样本诊断卡片' })).toBeInTheDocument();
  });

  it('shows unavailable provider status as unknown, not verified', async () => {
    vi.spyOn(apiClient, 'getModelExecutionStatus').mockRejectedValueOnce(new Error('状态读取失败'));
    const user = userEvent.setup();
    route();
    await screen.findByText('最近评测任务');
    const axes = screen.getByRole('button', { name: '查看运行模式状态' });
    expect(axes).toHaveTextContent('执行器未知');
    expect(axes).toHaveTextContent('提供方未知');
    await user.click(axes);
    expect(screen.getByRole('dialog')).toHaveTextContent('状态 API 读取失败');
    expect(axes).not.toHaveTextContent('真实已验证');
  });
});
