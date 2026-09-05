import type {
  DatasetStatus,
  ProviderConfigurationStatus,
  QualityStatus,
  QualityVerdict,
  Severity,
  TaskStatus,
} from '../types';

type BadgeValue = TaskStatus
  | DatasetStatus
  | Severity
  | QualityStatus
  | QualityVerdict
  | ProviderConfigurationStatus
  | 'succeeded'
  | 'partial_failed'
  | 'undetermined'
  | 'pending'
  | 'confirmed'
  | 'dismissed';

const labels: Record<BadgeValue, string> = {
  queued: '排队中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  succeeded: '执行成功',
  partial_failed: '部分执行失败',
  ready: '可用',
  indexing: '索引中',
  draft: '草稿',
  critical: '严重',
  warning: '警告',
  healthy: '健康',
  unknown: '未知',
  not_evaluated: '未评估',
  evaluated: '已评估',
  partial: '部分评估',
  error: '评估错误',
  legacy_unknown: '旧记录 / 未知',
  passed: '通过',
  undetermined: '无法判断',
  pending: '待复核',
  confirmed: '已确认',
  dismissed: '已排除',
  not_configured: '未配置',
  configured_unverified: '已配置 / 未验证',
  verified: '真实验证通过',
};

export function StatusBadge({ value }: { value: BadgeValue }) {
  return <span className={`status-badge status-${value}`}>{labels[value]}</span>;
}
