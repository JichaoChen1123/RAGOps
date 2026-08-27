import { X } from 'lucide-react';
import { useEffect, useId, type ReactNode } from 'react';

export function Dialog({
  open,
  title,
  eyebrow,
  children,
  footer,
  onClose,
}: {
  open: boolean;
  title: string;
  eyebrow?: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
}) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <header className="dialog-header">
          <div>{eyebrow && <span>{eyebrow}</span>}<h2 id={titleId}>{title}</h2></div>
          <button className="icon-button" type="button" aria-label={`关闭${title}`} onClick={onClose}><X size={17} /></button>
        </header>
        <div className="dialog-body">{children}</div>
        {footer && <footer className="dialog-footer">{footer}</footer>}
      </section>
    </div>
  );
}

export function Toast({ message, onDismiss }: { message: string | null; onDismiss: () => void }) {
  if (!message) return null;
  return (
    <div className="toast" role="status" aria-live="polite">
      <span>{message}</span>
      <button type="button" aria-label="关闭提示" onClick={onDismiss}><X size={14} /></button>
    </div>
  );
}
