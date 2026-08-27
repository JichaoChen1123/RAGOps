import { AlertTriangle, Database, RefreshCw } from 'lucide-react';

export function LoadingState({ label = '正在载入评测数据' }: { label?: string }) {
  return (
    <div className="state-panel" role="status" aria-live="polite">
      <div className="loading-mark" aria-hidden="true"><span /><span /><span /></div>
      <strong>{label}</strong>
      <p>正在同步任务、指标与证据，请稍候。</p>
      <div className="skeleton-grid" aria-hidden="true">
        <span /><span /><span /><span />
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="state-panel">
      <div className="state-icon"><Database size={22} /></div>
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state-panel state-error" role="alert">
      <div className="state-icon"><AlertTriangle size={22} /></div>
      <strong>数据载入失败</strong>
      <p>{message}</p>
      <button className="button button-secondary" type="button" onClick={onRetry}>
        <RefreshCw size={15} /> 重新请求
      </button>
    </div>
  );
}

export function PartialDataBanner({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <div className="partial-banner" role="status">
      <AlertTriangle size={16} />
      <span>{message}</span>
    </div>
  );
}

export function RefreshErrorBanner({
  subject,
  message,
  onRetry,
  retrying,
}: {
  subject: string;
  message: string;
  onRetry: () => void;
  retrying: boolean;
}) {
  return (
    <div className="refresh-error" role="alert">
      <AlertTriangle size={16} />
      <span>
        <strong>{subject}刷新失败</strong>
        <small>{message}。当前仍显示上次成功加载的数据。</small>
      </span>
      <button className="button button-small button-secondary" type="button" onClick={onRetry} disabled={retrying}>
        <RefreshCw className={retrying ? 'icon-spin' : undefined} size={14} />
        {retrying ? '重试中' : '重试刷新'}
      </button>
    </div>
  );
}
