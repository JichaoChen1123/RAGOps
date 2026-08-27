import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AppRoutes } from '../../frontend/src/App';

type RouteCase = {
  path: string;
  level: 1 | 2;
  heading: string;
};

type ActionCase = {
  path: string;
  actions: Array<{ role: 'button' | 'link'; name: string }>;
};

const criticalRoutes: RouteCase[] = [
  { path: '/projects/demo/overview', level: 2, heading: '客服 RAG 生产线' },
  { path: '/projects/demo/datasets', level: 2, heading: '数据集管理' },
  { path: '/projects/demo/evaluations', level: 2, heading: '评测任务' },
  {
    path: '/projects/demo/evaluations/eval-20260826/report',
    level: 2,
    heading: '客服知识库 v3 回归评测',
  },
  {
    path: '/projects/demo/evaluations/eval-20260826/samples/sample-042',
    level: 2,
    heading: '会员退款后，已发放的成长值会如何处理？',
  },
  { path: '/not-a-ragops-route', level: 1, heading: '页面不存在' },
];

const criticalActions: ActionCase[] = [
  {
    path: '/projects/demo/overview',
    actions: [
      { role: 'button', name: '刷新数据' },
      { role: 'button', name: '查看趋势看板' },
      { role: 'link', name: '新建评测' },
    ],
  },
  {
    path: '/projects/demo/datasets',
    actions: [
      { role: 'button', name: '导入数据' },
      { role: 'button', name: '新建数据集' },
      { role: 'button', name: '刷新数据集' },
      { role: 'button', name: '筛选' },
    ],
  },
  {
    path: '/projects/demo/evaluations',
    actions: [
      { role: 'button', name: '新建评测任务' },
      { role: 'button', name: '刷新任务状态' },
      { role: 'button', name: '筛选' },
      { role: 'link', name: '查看报告' },
    ],
  },
  {
    path: '/projects/demo/evaluations/eval-20260826/report',
    actions: [
      { role: 'button', name: '对比版本' },
      { role: 'button', name: '导出报告' },
      { role: 'link', name: '诊断样本 sample-042' },
    ],
  },
  {
    path: '/projects/demo/evaluations/eval-20260826/samples/sample-042',
    actions: [
      { role: 'button', name: '复制模型回答' },
      { role: 'button', name: '打开源文档' },
      { role: 'button', name: '排除诊断' },
      { role: 'button', name: '确认故障归因' },
    ],
  },
];

describe('critical route smoke gate', () => {
  it.each(criticalRoutes)(
    'renders $path without a route-level failure',
    async ({ path, level, heading }) => {
      render(
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>,
      );

      expect(await screen.findByRole('heading', { level, name: heading })).toBeInTheDocument();
    },
  );

  it.each(criticalActions)('exposes actionable MVP controls on $path', async ({ path, actions }) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    for (const action of actions) {
      const control = await screen.findByRole(action.role, { name: action.name });
      expect(control).toBeVisible();
      if (action.role === 'button') expect(control).toBeEnabled();
    }
  });
});
