import { Check, Circle, Clock3, Loader2, X } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { Target } from '../types/target';

const labels: Record<string, string> = {
  queued: 'Waiting for a check slot',
  opening_page: 'Open website',
  waiting_page_ready: 'Wait for page readiness',
  capturing: 'Capture page data',
  comparing: 'Compare with baselines',
  saving_result: 'Save result',
};

interface Props {
  target: Target;
  children: ReactNode;
  retry?: boolean;
  refreshFailed?: boolean;
}

export function CheckProgressPopover({ target, children, retry = false, refreshFailed = false }: Props) {
  const progress = target.check_progress;
  const active = Boolean((target.check_run_id && (target.status === 'Checking' || retry || progress?.state === 'queued' || progress?.state === 'retry_wait')) || progress?.state === 'finished');
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pinnedRef = useRef(false);
  const suppressFocusRef = useRef(false);
  const id = useId();

  const clearTimers = useCallback(() => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    hoverTimer.current = null;
    closeTimer.current = null;
  }, []);
  const dismiss = useCallback((restorePanelFocus: boolean) => {
    const focusWasInPanel = Boolean(panelRef.current?.contains(document.activeElement));
    clearTimers();
    pinnedRef.current = false;
    setPinned(false);
    setOpen(false);
    if (restorePanelFocus && focusWasInPanel && triggerRef.current) {
      suppressFocusRef.current = true;
      triggerRef.current.focus();
    }
  }, [clearTimers]);

  const startAt = progress?.attempt_started_at;
  useEffect(() => {
    if (!open || !active || !startAt || progress?.state === 'finished') return;
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - Date.parse(startAt)) / 1000)));
    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [open, active, startAt, progress?.state]);

  useEffect(() => {
    if (!open) return;
    const place = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(336, window.innerWidth - 24);
      setPosition({
        top: Math.max(12, Math.min(rect.bottom + 8, window.innerHeight - 270)),
        left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)),
      });
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!triggerRef.current?.contains(event.target as Node) && !panelRef.current?.contains(event.target as Node)) {
        dismiss(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        dismiss(true);
      }
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, dismiss]);

  useEffect(() => () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }, []);

  if (!active) return <>{children}</>;

  const requestOpen = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = null;
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hoverTimer.current = setTimeout(() => {
      hoverTimer.current = null;
      setOpen(true);
    }, 300);
  };
  const requestClose = () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => {
      closeTimer.current = null;
      if (!pinnedRef.current && !panelRef.current?.contains(document.activeElement)) setOpen(false);
    }, 140);
  };
  const steps = progress?.steps ?? [];
  const orderedPhases = ['queued', 'opening_page', 'waiting_page_ready', 'capturing', 'comparing', 'saving_result'];
  const currentPhase = progress?.phase;
  const terminal = progress?.state === 'finished';

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="inline-flex rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
        aria-label={retry ? 'View check retry progress' : 'View check progress'}
        aria-expanded={open}
        aria-controls={id}
        onMouseEnter={requestOpen}
        onMouseLeave={requestClose}
        onFocus={() => {
          if (suppressFocusRef.current) {
            suppressFocusRef.current = false;
            return;
          }
          clearTimers();
          setOpen(true);
        }}
        onBlur={(event) => {
          if (!panelRef.current?.contains(event.relatedTarget as Node)) requestClose();
        }}
        onClick={() => {
          if (closeTimer.current) clearTimeout(closeTimer.current);
          if (pinned) {
            pinnedRef.current = false;
            setPinned(false);
            setOpen(false);
          } else {
            pinnedRef.current = true;
            setPinned(true);
            setOpen(true);
          }
        }}
      >
        {children}
      </button>
      {open && createPortal(
        <div
          ref={panelRef}
          id={id}
          role="region"
          aria-label="Check progress"
          style={{ position: 'fixed', top: position.top, left: position.left, width: 'min(336px, calc(100vw - 24px))', zIndex: 1000 }}
          className="rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl shadow-black/40"
          onMouseEnter={() => {
            if (closeTimer.current) clearTimeout(closeTimer.current);
            closeTimer.current = null;
            if (hoverTimer.current) clearTimeout(hoverTimer.current);
            hoverTimer.current = null;
          }}
          onMouseLeave={requestClose}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="font-semibold text-slate-100">
              {terminal ? `Check ${progress?.outcome ?? target.status}` : retry ? 'Retry scheduled' : currentPhase ? labels[currentPhase] : 'Check requested'}
            </div>
            <button type="button" className="rounded p-1 text-slate-400 hover:text-white" aria-label="Close progress" onClick={() => dismiss(true)}><X size={15} /></button>
          </div>
          <div className="mt-1 text-xs text-slate-400">
            {retry ? `Retry ${Math.min((target.check_attempt_count ?? 0) + 1, target.check_retry_max_attempts ?? 3)}/${target.check_retry_max_attempts ?? 3}` : `Elapsed: ${elapsed}s · Attempt ${Math.max(1, progress?.attempt_number ?? target.check_attempt_count ?? 1)}/${target.check_retry_max_attempts ?? 3}`}
          </div>
          <span className="sr-only" role="status" aria-live="polite">
            {terminal ? `Check finished with status ${progress?.outcome ?? target.status}` : `Check phase: ${labels[currentPhase ?? 'queued'] ?? currentPhase}`}
          </span>
          {!progress && <p className="mt-3 text-xs text-slate-400">Progress details unavailable · Waiting for status refresh</p>}
          {refreshFailed && <p role="status" className="mt-3 text-xs text-amber-300">Unable to refresh progress · Showing the last known status</p>}
          {progress?.error_code === 'attempt_finalization_unconfirmed' && <p role="status" className="mt-3 text-xs text-amber-300">Check result is known, but attempt finalization could not be confirmed.</p>}
          {progress && <div className="mt-3 space-y-2">
            {orderedPhases.map((phase) => {
              const step = [...steps].reverse().find((item) => item.phase === phase);
              const state = step?.state ?? 'pending';
              const Icon = state === 'completed' ? Check : state === 'running' ? Loader2 : state === 'retry_wait' ? Clock3 : state === 'failed' ? X : Circle;
              const label = labels[phase] ?? phase;
              return <div key={phase} className="flex items-center gap-2 text-xs">
                <Icon size={14} className={state === 'completed' ? 'text-emerald-400' : state === 'failed' ? 'text-rose-400' : state === 'running' ? 'animate-spin text-cyan-400 motion-reduce:animate-none' : 'text-slate-500'} />
                <span className={state === 'running' ? 'text-cyan-200' : 'text-slate-300'}>{state === 'completed' ? 'Done' : state === 'running' ? 'Running' : state === 'skipped' ? 'Skipped' : state === 'retry_wait' ? 'Waiting' : state === 'failed' ? 'Failed' : 'Pending'} · {label}</span>
              </div>;
            })}
            {retry && target.next_check_at && <div className="pt-1 text-xs text-amber-300">Next attempt · {new Date(target.next_check_at).toLocaleString()}</div>}
            {progress.state === 'finished' && <div className="pt-1 text-xs text-slate-400">Finished · {progress.outcome}</div>}
            {progress.state !== 'finished' && <div className="pt-1 text-[11px] text-slate-500">Updated {new Date(progress.updated_at).toLocaleTimeString()}</div>}
          </div>}
        </div>, document.body)}
    </>
  );
}
