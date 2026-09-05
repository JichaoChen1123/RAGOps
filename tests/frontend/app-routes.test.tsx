import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AppRoutes } from '../../frontend/src/App';

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('RAGOps MVP routes', () => {
  it('navigates from evaluation tasks to report and sample evidence', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/evaluations');

    expect(await screen.findByRole('heading', { level: 2, name: '评测任务' })).toBeInTheDocument();
    await user.click((await screen.findAllByRole('link', { name: /查看报告/ }))[0]);

    expect(await screen.findByRole('heading', { level: 2, name: '客服知识库 v3 回归评测' })).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '诊断样本 sample-042' }));

    expect(await screen.findByRole('heading', { level: 2, name: '会员退款后，已发放的成长值会如何处理？' })).toBeInTheDocument();
    expect(screen.getByText('关键政策文档未进入 Top 5')).toBeInTheDocument();
    expect(screen.getByText('会员成长值规则（2026 生效）')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /\[2\].*不支持/ }));
    expect(screen.getByRole('heading', { level: 3, name: '订单退款通用规则' })).toBeInTheDocument();
  });

  it('renders an explicit empty state for datasets', async () => {
    renderRoute('/projects/demo/datasets?state=empty');
    expect(await screen.findByText('还没有数据集')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /导入首个数据集/ })).toBeInTheDocument();
  });

  it('renders and retries the error state without hiding the cause', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/overview?state=error');
    expect(await screen.findByRole('alert')).toHaveTextContent('评测服务暂时不可用');
    await user.click(screen.getByRole('button', { name: '重新请求' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('评测服务暂时不可用');
  });

  it('switches to partial data and preserves an undetermined gate', async () => {
    const user = userEvent.setup();
    renderRoute('/projects/demo/evaluations/eval-20260826/report');
    expect(await screen.findByText('质量门结论')).toBeInTheDocument();

    await user.selectOptions(screen.getByRole('combobox', { name: '数据场景' }), 'partial');
    expect((await screen.findAllByText(/部分指标仍在计算/)).length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { level: 3, name: '未知' })).toBeInTheDocument();
    expect(screen.getAllByText('未评估').length).toBeGreaterThan(0);
  });
});
