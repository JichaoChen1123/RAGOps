import { ArrowDownRight, ArrowUpRight, CircleDashed } from 'lucide-react';
import { formatMetric, formatUnknownStatus } from '../lib/format';
import type { MetricValue } from '../types';

export function MetricCard({ metric, compact = false }: { metric: MetricValue; compact?: boolean }) {
  const isUnavailable = metric.value === null;
  const reachedThreshold = typeof metric.value === 'number' && metric.status === 'ok' && metric.threshold !== undefined
    ? metric.direction === 'lower'
      ? metric.value <= metric.threshold
      : metric.value >= metric.threshold
    : undefined;

  return (
    <article className={`metric-card ${compact ? 'metric-card-compact' : ''} ${isUnavailable ? 'metric-unavailable' : ''}`}>
      <div className="metric-head">
        <span>{metric.label}</span>
        {reachedThreshold !== undefined && (
          <span className={`metric-gate ${reachedThreshold ? 'gate-pass' : 'gate-fail'}`}>
            {reachedThreshold ? '达标' : '未达标'}
          </span>
        )}
      </div>
      <div className="metric-value">
        {isUnavailable && <CircleDashed size={18} />}
        {formatMetric(metric.value, metric.unit, metric.status)}
      </div>
      <div className="metric-meta">
        {metric.delta !== undefined && metric.delta !== null ? (
          <span className={metric.delta >= 0 ? 'delta-up' : 'delta-down'}>
            {metric.delta >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
            {Math.abs(metric.delta).toFixed(1)}% 较上次
          </span>
        ) : isUnavailable ? (
          <span>{formatUnknownStatus(metric.status)}</span>
        ) : metric.threshold !== undefined ? (
          <span>门槛 {formatMetric(metric.threshold, metric.unit, 'ok')}</span>
        ) : (
          <span>暂无基线</span>
        )}
      </div>
    </article>
  );
}
