import type { DatasetStatus, Severity, TaskStatus } from '../types';

type BadgeValue = TaskStatus | DatasetStatus | Severity | 'passed' | 'failed' | 'undetermined' | 'pending' | 'confirmed' | 'dismissed';

const labels: Record<BadgeValue, string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  ready: '可用',
  indexing: '索引中',
  draft: '草稿',
  critical: '严重',
  warning: '警告',
  healthy: '健康',
  unknown: '未知',
  passed: '通过',
  undetermined: '无法判断',
  pending: '待复核',
  confirmed: '已确认',
  dismissed: '已排除',
};

export function StatusBadge({ value }: { value: BadgeValue }) {
  return <span className={`status-badge status-${value}`}>{labels[value]}</span>;
}
