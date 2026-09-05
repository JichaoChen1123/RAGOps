export function formatDateTime(value?: string): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value));
}

import type { MetricStatus } from '../types';

export function formatUnknownStatus(status?: MetricStatus): string {
  if (status === 'not_evaluated') return '未评估';
  if (status === 'not_applicable') return '不适用';
  if (status === 'error') return '评估错误';
  if (status === 'legacy') return '旧记录 / 未知';
  return '未知';
}

export function formatMetric(value: number | boolean | null, unit?: string, status?: MetricStatus): string {
  if (value === null) return formatUnknownStatus(status);
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (unit === 'USD') return `$${value.toFixed(3)}`;
  return `${Number.isInteger(value) ? value : value.toFixed(1)}${unit ?? ''}`;
}

export function formatScore(value: number | null, status?: MetricStatus): string {
  if (value === null) return formatUnknownStatus(status);
  return value <= 1 ? value.toFixed(2) : value.toFixed(1);
}
