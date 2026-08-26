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

export function formatMetric(value: number | null, unit?: string): string {
  if (value === null) return '不可计算';
  if (unit === 'USD') return `$${value.toFixed(3)}`;
  return `${Number.isInteger(value) ? value : value.toFixed(1)}${unit ?? ''}`;
}

export function formatScore(value: number | null): string {
  if (value === null) return '—';
  return value <= 1 ? value.toFixed(2) : value.toFixed(1);
}
