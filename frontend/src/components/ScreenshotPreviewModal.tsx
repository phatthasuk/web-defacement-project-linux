import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { ScreenshotCompare } from './ScreenshotCompare';
import {
  useTargetBaselineSnapshotQuery,
  useTargetChecksQuery,
  useTargetSnapshotsQuery,
} from '../hooks/useTargetDetail';
import type { Target } from '../types/target';
import { getScreenshotComparisonIds } from '../utils/screenshotComparison';

interface ScreenshotPreviewModalProps {
  target: Target;
  onClose: () => void;
}

export function ScreenshotPreviewModal({ target, onClose }: ScreenshotPreviewModalProps) {
  const [isZoomOpen, setIsZoomOpen] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const { data: snapshots, isLoading: isSnapshotsLoading, isError: snapshotsError, refetch: refetchSnapshots } = useTargetSnapshotsQuery(target.id);
  const { data: baselineSnapshot, isLoading: isBaselineLoading, isError: baselineError, refetch: refetchBaseline } = useTargetBaselineSnapshotQuery(target.id);
  const { data: checks, isLoading: isChecksLoading, isError: checksError, refetch: refetchChecks } = useTargetChecksQuery(target.id);

  const { baselineSnapshotId, currentSnapshotId } =
    getScreenshotComparisonIds(target, snapshots, baselineSnapshot, checks);
  const isLoading = isSnapshotsLoading || isBaselineLoading || isChecksLoading;
  const hasError = snapshotsError || baselineError || checksError;
  const titleId = `screenshot-preview-title-${target.id}`;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && !isZoomOpen) {
      event.stopPropagation();
      onClose();
      return;
    }

    if (event.key !== 'Tab') return;
    const focusable = event.currentTarget.querySelectorAll<HTMLElement>(
      'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/80 p-3 backdrop-blur-sm sm:p-6"
      onClick={onClose}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={handleKeyDown}
        className="flex max-h-[94vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-950 shadow-2xl"
      >
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-800 px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="truncate text-lg font-semibold text-slate-100">
              {target.name}
            </h2>
            <a href={target.url} target="_blank" rel="noopener noreferrer" className="block truncate text-xs text-slate-500 hover:text-cyan-400">
              {target.url}
            </a>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close screenshot preview"
            className="shrink-0 rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-5">
          {isLoading ? (
            <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-sm text-slate-400" role="status">
              <svg className="h-7 w-7 animate-spin text-cyan-400" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading screenshot comparison...
            </div>
          ) : hasError ? (
            <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center" role="alert">
              <p className="text-sm text-rose-300">Could not load screenshot comparison data.</p>
              <button
                type="button"
                onClick={() => {
                  if (snapshotsError) void refetchSnapshots();
                  if (baselineError) void refetchBaseline();
                  if (checksError) void refetchChecks();
                }}
                className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800"
              >
                Retry
              </button>
            </div>
          ) : (
            <ScreenshotCompare
              baselineSnapshotId={baselineSnapshotId}
              currentSnapshotId={currentSnapshotId}
              onZoomChange={setIsZoomOpen}
            />
          )}
        </div>
      </section>
    </div>
  );
}
