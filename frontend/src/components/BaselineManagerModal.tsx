import { useState, useEffect, useCallback } from 'react';
import { Snapshot } from '../types/snapshot';
import { BASE_URL } from '../api/client';
import { formatDateTime } from '../utils/date';

interface BaselineManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  targetId: string;
  targetName: string;
  latestMatchedSnapshotId?: string | null;
  baselines: Snapshot[];
  isLoading: boolean;
  onDemote: (snapshotId: string) => Promise<void>;
  isDemoting: boolean;
  maxBaselines?: number;
}

export function BaselineManagerModal({
  isOpen,
  onClose,
  targetName,
  latestMatchedSnapshotId,
  baselines,
  isLoading,
  onDemote,
  isDemoting,
  maxBaselines = 20,
}: BaselineManagerModalProps) {
  const [confirmDemoteId, setConfirmDemoteId] = useState<string | null>(null);
  const [demoteError, setDemoteError] = useState<string | null>(null);
  const [zoomedImage, setZoomedImage] = useState<{ src: string; label: string } | null>(null);

  // Close on Escape
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (zoomedImage) {
          setZoomedImage(null);
        } else if (confirmDemoteId) {
          setConfirmDemoteId(null);
        } else {
          onClose();
        }
      }
    },
    [zoomedImage, confirmDemoteId, onClose]
  );

  useEffect(() => {
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    } else {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  // The backend refuses to remove the last baseline: with none left, the next
  // check would adopt the live page as the new baseline without review. The
  // button below is disabled in that case, so this only fires on a race.
  const isLastBaseline = baselines.length <= 1;

  const handleConfirmDemote = async (snapshotId: string) => {
    setDemoteError(null);
    try {
      await onDemote(snapshotId);
      setConfirmDemoteId(null);
    } catch (err) {
      setDemoteError(err instanceof Error ? err.message : 'Could not remove this baseline.');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Manage Baselines for ${targetName}`}
      className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 md:p-6"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/80">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-slate-100">Manage Baselines</h2>
            <span className="text-xs text-slate-400 font-normal">({targetName})</span>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-800/60 text-cyan-400 font-mono">
              {baselines.length} / {maxBaselines} Active
            </span>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close baseline manager"
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {demoteError && (
            <div
              role="alert"
              className="bg-rose-950/20 border border-rose-800/40 rounded-xl px-4 py-3 text-sm text-rose-300"
            >
              {demoteError}
            </div>
          )}
          {isLoading ? (
            <div className="flex flex-col items-center justify-center p-12 text-slate-400 gap-3">
              <svg className="animate-spin h-7 w-7 text-cyan-400" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>Loading baselines...</span>
            </div>
          ) : baselines.length === 0 ? (
            <div className="border border-slate-800 border-dashed rounded-xl p-12 text-center text-slate-500">
              <p className="text-base font-medium">No baselines approved yet.</p>
              <p className="text-xs text-slate-600 mt-1">
                When checks run, you can approve captures as baselines to train the multi-baseline engine.
              </p>
            </div>
          ) : (
            <>
              <div className="text-xs text-slate-400 bg-slate-950/60 p-3 rounded-lg border border-slate-800 flex items-center justify-between">
                <span>
                  The system matches incoming checks against <strong>all active baselines</strong> and scores against the closest variant.
                </span>
                <span className="text-[11px] text-slate-500">Max limit: 20 per target</span>
              </div>

              {/* Grid of Baselines */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {baselines.map((baseline, idx) => {
                  const isLatestMatch = latestMatchedSnapshotId === baseline.id;
                  const isConfirming = confirmDemoteId === baseline.id;
                  const imgSrc = `${BASE_URL}/snapshots/${baseline.id}/screenshot`;

                  return (
                    <div
                      key={baseline.id}
                      className={`flex flex-col rounded-xl border overflow-hidden transition-all bg-slate-950/60 ${
                        isLatestMatch
                          ? 'border-emerald-500/60 shadow-emerald-950/30 shadow-md'
                          : 'border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      {/* Card Top Label */}
                      <div className="px-3 py-2 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-300">
                          Baseline #{idx + 1}
                        </span>
                        {isLatestMatch && (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-950 border border-emerald-700/60 text-emerald-400 font-medium flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                            Latest Match
                          </span>
                        )}
                      </div>

                      {/* Thumbnail with Zoom Click */}
                      <div
                        className="relative h-44 bg-slate-950 flex items-center justify-center overflow-hidden cursor-zoom-in group border-b border-slate-800/80"
                        onClick={() =>
                          setZoomedImage({
                            src: imgSrc,
                            label: `Baseline #${idx + 1} (${formatDateTime(baseline.captured_at)})`,
                          })
                        }
                        title="Click to view full resolution"
                      >
                        <img
                          src={imgSrc}
                          alt={`Baseline ${idx + 1}`}
                          className="max-h-full max-w-full object-contain transition-transform duration-300 group-hover:scale-105"
                          loading="lazy"
                        />
                        <div className="absolute inset-0 bg-slate-950/0 group-hover:bg-slate-950/30 transition-colors flex items-center justify-center pointer-events-none">
                          <span className="opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900/90 text-cyan-300 text-[11px] px-2.5 py-1 rounded-full border border-cyan-800/60 shadow">
                            🔍 Zoom
                          </span>
                        </div>
                      </div>

                      {/* Card Metadata */}
                      <div className="p-3.5 space-y-2 flex-1 flex flex-col justify-between text-xs">
                        <div className="space-y-1.5">
                          <div>
                            <span className="text-slate-500 block text-[10px] uppercase">Captured At</span>
                            <span className="text-slate-200 font-medium">
                              {formatDateTime(baseline.captured_at)}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[10px] uppercase">Title</span>
                            <span className="text-slate-300 truncate block italic">
                              {baseline.title || 'No Title'}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[10px] uppercase">Snapshot ID</span>
                            <span className="font-mono text-slate-400 text-[10px] truncate block">
                              {baseline.id}
                            </span>
                          </div>
                        </div>

                        {/* Action Area */}
                        <div className="pt-3 border-t border-slate-800/60">
                          {isConfirming ? (
                            <div className="space-y-2 bg-rose-950/30 border border-rose-800/40 p-2.5 rounded-lg">
                              <p className="text-[11px] text-rose-300 font-medium">
                                Remove this baseline from active rotation?
                              </p>
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  disabled={isDemoting}
                                  onClick={() => handleConfirmDemote(baseline.id)}
                                  className="flex-1 text-[11px] py-1 px-2 rounded bg-rose-600 hover:bg-rose-500 text-white font-medium transition-colors"
                                >
                                  {isDemoting ? 'Removing...' : 'Confirm Remove'}
                                </button>
                                <button
                                  type="button"
                                  disabled={isDemoting}
                                  onClick={() => setConfirmDemoteId(null)}
                                  className="text-[11px] py-1 px-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          ) : isLastBaseline ? (
                            <p className="py-1.5 px-2.5 rounded border border-slate-800 bg-slate-900/40 text-slate-500 text-[11px] leading-snug">
                              This is the only baseline and cannot be removed. Approve
                              another snapshot first, otherwise the next check would
                              adopt the live page as the baseline without review.
                            </p>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setConfirmDemoteId(baseline.id)}
                              className="w-full text-left py-1.5 px-2.5 rounded border border-rose-900/40 text-rose-400 hover:bg-rose-950/30 hover:border-rose-800/60 transition-colors text-[11px] font-medium flex items-center justify-between"
                            >
                              <span>Remove from Baselines</span>
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-900/80 flex items-center justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium transition-colors"
          >
            Done
          </button>
        </div>
      </div>

      {/* Fullscreen Zoom Modal */}
      {zoomedImage && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={zoomedImage.label}
          className="fixed inset-0 z-60 bg-slate-950/90 backdrop-blur-md flex flex-col p-4 md:p-6"
          onClick={() => setZoomedImage(null)}
        >
          <div
            className="flex items-center justify-between pb-3 border-b border-slate-800 text-slate-200 shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold text-lg text-slate-100">{zoomedImage.label}</h3>
            <button
              type="button"
              onClick={() => setZoomedImage(null)}
              aria-label="Close zoomed image"
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div
            className="flex-1 overflow-auto mt-4 flex justify-center items-start cursor-zoom-out p-2"
            onClick={() => setZoomedImage(null)}
          >
            <img
              src={zoomedImage.src}
              alt={zoomedImage.label}
              className="max-w-none w-auto max-h-none rounded-lg shadow-2xl border border-slate-800/80 cursor-default"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </div>
  );
}
