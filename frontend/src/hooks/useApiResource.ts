import { useCallback, useEffect, useState } from 'react';
import type { ViewScenario } from '../types';

export type ResourceState<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: T; partialMessage?: string };

interface ResourceOptions<T> {
  scenario: ViewScenario;
  emptyValue: T;
  partialize?: (data: T) => T;
}

export function useApiResource<T>(
  loader: () => Promise<T>,
  dependencies: readonly unknown[],
  options: ResourceOptions<T>,
) {
  const [state, setState] = useState<ResourceState<T>>({ status: 'loading' });
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    if (options.scenario === 'loading') return;
    if (options.scenario === 'error') {
      setState({ status: 'error', message: '评测服务暂时不可用，请检查 API 连接或稍后重试。' });
      return;
    }

    try {
      const result = await loader();
      if (options.scenario === 'empty') {
        setState({ status: 'success', data: options.emptyValue });
        return;
      }
      if (options.scenario === 'partial') {
        setState({
          status: 'success',
          data: options.partialize ? options.partialize(result) : result,
          partialMessage: '部分指标仍在计算，当前结果仅用于排查，不应作为发布门禁结论。',
        });
        return;
      }
      setState({ status: 'success', data: result });
    } catch (error) {
      setState({
        status: 'error',
        message: error instanceof Error ? error.message : '发生未知错误',
      });
    }
  // dependencies are intentionally controlled by each page.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, options.scenario, refreshKey]);

  useEffect(() => {
    void load();
  }, [load]);

  return { state, retry: () => setRefreshKey((key) => key + 1) };
}
