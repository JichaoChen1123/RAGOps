import type { FailureBucket } from '../types';

export function FailureChart({ buckets }: { buckets: FailureBucket[] }) {
  const total = buckets.reduce((sum, bucket) => sum + bucket.count, 0);
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1);

  return (
    <div className="failure-chart" aria-label={`失败类型分布，共 ${total} 条`}>
      <div className="donut" style={{ '--critical-ratio': `${total ? (buckets[0]?.count ?? 0) / total * 100 : 0}%` } as React.CSSProperties}>
        <div><strong>{total}</strong><span>失败样本</span></div>
      </div>
      <div className="failure-bars">
        {buckets.map((bucket) => (
          <div className="failure-row" key={bucket.key}>
            <div><span>{bucket.label}</span><strong>{bucket.count}</strong></div>
            <span className="bar-track"><span className={`bar-fill bar-${bucket.severity}`} style={{ width: `${bucket.count / max * 100}%` }} /></span>
          </div>
        ))}
      </div>
    </div>
  );
}
