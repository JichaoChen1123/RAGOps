import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AppRoutes } from '../../frontend/src/App';

type RouteCase = {
  path: string;
  level: 1 | 2;
  heading: string;
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
});
