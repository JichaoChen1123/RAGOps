import { ChevronLeft, ChevronRight, Layers3 } from 'lucide-react';
import { useId, useState, type CSSProperties, type ReactNode } from 'react';

/** Only the active record mounts its controls; rear layers are selectable previews. */
export function CardStack<T extends { id: string }>({
  items, label, getLabel, renderItem,
}: {
  items: T[];
  label: string;
  getLabel: (item: T) => string;
  renderItem: (item: T) => ReactNode;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const helpId = useId();
  const selectedIndex = Math.max(0, items.findIndex((item) => item.id === selectedId));
  const select = (index: number) => {
    if (items.length) setSelectedId(items[(index + items.length) % items.length].id);
  };
  if (!items.length) return <p className="stack-empty">暂无可浏览记录。</p>;
  const visible = Array.from({ length: Math.min(items.length, 3) }, (_, depth) => ({
    item: items[(selectedIndex + depth) % items.length], depth,
  })).reverse();

  return (
    <section className="card-stack" role="region" aria-roledescription="卡片轮播" aria-label={label}
      tabIndex={0} aria-describedby={helpId}
      onKeyDown={(event) => {
        // Leave editing, links and any nested widgets their own key behavior.
        if (event.target !== event.currentTarget && !(event.target as HTMLElement).closest('.stack-controls')) return;
        const next = { ArrowLeft: selectedIndex - 1, ArrowRight: selectedIndex + 1, Home: 0, End: items.length - 1 }[event.key];
        if (next !== undefined) { event.preventDefault(); select(next); }
      }}>
      <div className="stack-controls">
        <span className="stack-count" aria-live="polite" aria-atomic="true"><Layers3 size={16} />{selectedIndex + 1} / {items.length}</span>
        <span className="stack-hint" id={helpId}>点击翻阅 · ← → 切换</span>
        <button type="button" className="icon-button" aria-label={`${label}：上一项`} disabled={items.length < 2} onClick={() => select(selectedIndex - 1)}><ChevronLeft size={18} /></button>
        <button type="button" className="icon-button" aria-label={`${label}：下一项`} disabled={items.length < 2} onClick={() => select(selectedIndex + 1)}><ChevronRight size={18} /></button>
      </div>
      <div className="stack-stage" style={{ '--layers': visible.length - 1 } as CSSProperties}>
        {visible.map(({ item, depth }) => (
          <div key={item.id} className={`stack-sheet stack-depth-${depth}`} style={{ zIndex: 3 - depth }}>
            {depth === 0 ? <article className="stack-record" aria-label={getLabel(item)}>{renderItem(item)}</article> : (
              <button className="stack-peek" type="button" aria-label={`翻阅：${getLabel(item)}`} onClick={() => {
                select(selectedIndex + depth);
                // The preview will unmount; retain an intentional keyboard focus target.
                document.getElementById(helpId)?.closest<HTMLElement>('.card-stack')?.focus({ preventScroll: true });
              }}><span>待浏览</span><span>{String((selectedIndex + depth) % items.length + 1).padStart(2, '0')}</span></button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
