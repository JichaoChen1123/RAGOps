import type { TrendPoint } from '../types';

export function TrendChart({ points }: { points: TrendPoint[] }) {
  const width = 560;
  const height = 150;
  const padding = 18;
  const min = Math.min(...points.map((point) => point.score), 0);
  const max = Math.max(...points.map((point) => point.score), 100);
  const plotWidth = width - padding * 2;
  const plotHeight = height - padding * 2;
  const coords = points.map((point, index) => ({
    x: padding + (index / Math.max(points.length - 1, 1)) * plotWidth,
    y: padding + (1 - (point.score - min) / Math.max(max - min, 1)) * plotHeight,
    ...point,
  }));
  const path = coords.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`).join(' ');
  const area = `${path} L ${coords.at(-1)?.x ?? padding} ${height - padding} L ${padding} ${height - padding} Z`;

  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="最近七次评测质量趋势">
        <defs>
          <linearGradient id="trendArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#5b8def" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#5b8def" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((ratio) => <line key={ratio} x1={padding} x2={width - padding} y1={padding + plotHeight * ratio} y2={padding + plotHeight * ratio} className="grid-line" />)}
        <path d={area} fill="url(#trendArea)" />
        <path d={path} className="trend-line" />
        {coords.map((point) => <circle key={point.label} cx={point.x} cy={point.y} r="4" className="trend-dot"><title>{point.label}: {point.score}</title></circle>)}
      </svg>
      <div className="chart-labels">{points.map((point) => <span key={point.label}>{point.label}</span>)}</div>
    </div>
  );
}
