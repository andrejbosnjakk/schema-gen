// Small shared pieces: UI glyphs, a menu button, toasts, a dialog.
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

const G: Record<string, ReactNode> = {
  plus: <path d="M8 3.5v9M3.5 8h9" />, minus: <path d="M3.5 8h9" />,
  fit: <path d="M3 6V3h3M10 3h3v3M13 10v3h-3M6 13H3v-3" />,
  down: <path d="M4.5 6.5 8 10l3.5-3.5" />, up: <path d="M4.5 9.5 8 6l3.5 3.5" />, left: <path d="M9.5 4.5 6 8l3.5 3.5" />,
  sun: <><circle cx="8" cy="8" r="2.75" /><path d="M8 1.75v1.5M8 12.75v1.5M1.75 8h1.5M12.75 8h1.5M3.6 3.6l1 1M11.4 11.4l1 1M3.6 12.4l1-1M11.4 4.6l1-1" /></>,
  moon: <path d="M12.9 9.8A5.25 5.25 0 0 1 6.2 3.1a5.25 5.25 0 1 0 6.7 6.7Z" />,
  help: <><circle cx="8" cy="8" r="6.25" /><path d="M6.3 6.3a1.8 1.8 0 1 1 2.4 1.7c-.5.2-.7.6-.7 1.1v.3" /><circle cx="8" cy="11.4" r=".4" fill="currentColor" /></>,
  upload: <path d="M8 10.5V3M5 6l3-3 3 3M3 10.5v1.75c0 .7.55 1.25 1.25 1.25h7.5c.7 0 1.25-.55 1.25-1.25V10.5" />,
  play: <path d="M5 3.5v9l7-4.5-7-4.5Z" />, x: <path d="M4 4l8 8M12 4l-8 8" />,
  file: <><path d="M4 1.75h5L12 4.75v9.5H4z" /><path d="M9 1.75v3h3" /></>,
  search: <><circle cx="7" cy="7" r="4.25" /><path d="M10.2 10.2 13.5 13.5" /></>,
  download: <path d="M8 2.5V10M5 7l3 3 3-3M3 12.5h10" />,
};
export function Glyph({ name, size = 16 }: { name: keyof typeof G | string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{G[name]}</svg>;
}

/** A button that opens a small menu; closes on a pick, Escape or a click elsewhere. */
export function MenuButton({ label, icon, items, tour, align = "right", iconOnly }: {
  label: string; icon?: string; items: { label: string; hint?: string; run: () => void }[]; tour?: string; align?: "left" | "right"; iconOnly?: boolean }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null), id = useId();
  useEffect(() => {
    if (!open) return;
    box.current?.querySelector<HTMLButtonElement>("[role=menuitem]")?.focus();
    const off = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setOpen(false); box.current?.querySelector<HTMLButtonElement>("button")?.focus(); }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        const its = [...(box.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? [])], i = its.indexOf(document.activeElement as HTMLButtonElement);
        its[(i + (e.key === "ArrowDown" ? 1 : its.length - 1)) % its.length]?.focus(); e.preventDefault();
      }
    };
    document.addEventListener("mousedown", off); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", off); document.removeEventListener("keydown", key); };
  }, [open]);
  return (
    <div className="menu-wrap" ref={box}>
      <button className={iconOnly ? "btn btn-ghost btn-icon" : "btn"} aria-haspopup="menu" aria-expanded={open} aria-controls={id} data-tour={tour}
              onClick={() => setOpen((o) => !o)} aria-label={iconOnly ? label : undefined} title={iconOnly ? label : undefined}>
        {icon && <Glyph name={icon} />}{!iconOnly && <>{label}<Glyph name="down" size={14} /></>}
      </button>
      {open && <div className={`menu anim-pop ${align}`} role="menu" id={id} aria-label={label}>
        {items.map((it) => <button key={it.label} role="menuitem" className="menu-item" onClick={() => { setOpen(false); it.run(); }}>
          <span>{it.label}</span>{it.hint && <span className="menu-hint">{it.hint}</span>}</button>)}
      </div>}
    </div>);
}

export interface Toast { id: number; tone: "info" | "ok" | "err"; text: string; action?: { label: string; run: () => void } }
export function Toasts({ list, close }: { list: Toast[]; close: (id: number) => void }) {
  return <div className="toasts" role="status" aria-live="polite">
    {list.map((t) => <div key={t.id} className={`toast anim-pop ${t.tone}`}>
      <span className="toast-text">{t.text}</span>
      {t.action && <button className="btn btn-sm" onClick={() => { close(t.id); t.action!.run(); }}>{t.action.label}</button>}
      <button className="btn btn-ghost btn-icon btn-sm" onClick={() => close(t.id)} aria-label="Dismiss"><Glyph name="x" size={14} /></button>
    </div>)}
  </div>;
}

/** A centred dialog over a scrim; Escape or the scrim closes it. */
export function Dialog({ title, onClose, children, tour }: { title: ReactNode; onClose: () => void; children?: ReactNode; tour?: string }) {
  const id = useId(), close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); prev?.focus?.(); };
  }, [onClose]);
  return <div className="scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="dialog anim-pop" role="dialog" aria-modal="true" aria-labelledby={id} data-tour={tour}>
      <header><h2 id={id}>{title}</h2><button ref={close} className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Close"><Glyph name="x" /></button></header>
      <section>{children}</section>
    </div>
  </div>;
}
