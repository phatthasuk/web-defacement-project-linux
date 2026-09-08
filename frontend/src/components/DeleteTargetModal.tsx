import { useState, useEffect, useCallback } from 'react';
import { Target } from '../types/target';
import { ApiError } from '../api/client';

interface DeleteTargetModalProps {
  isOpen: boolean;
  onClose: () => void;
  target: Target | null;
  onConfirm: (targetId: string) => Promise<void>;
  isDeleting: boolean;
}

export function DeleteTargetModal({
  isOpen,
  onClose,
  target,
  onConfirm,
  isDeleting,
}: DeleteTargetModalProps) {
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setDeleteError(null);
    }
  }, [isOpen]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isDeleting) {
        onClose();
      }
    },
    [isDeleting, onClose]
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

  if (!isOpen || !target) return null;

  const handleConfirmDelete = async () => {
    setDeleteError(null);
    try {
      await onConfirm(target.id);
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setDeleteError(err.detail);
      } else if (err instanceof Error) {
        setDeleteError(err.message);
      } else {
        setDeleteError('Failed to delete target. Please try again.');
      }
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Delete Target ${target.name}`}
      className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4"
      onClick={() => {
        if (!isDeleting) onClose();
      }}
    >
      <div
        className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header / Warning Icon */}
        <div className="p-6">
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-800/60 text-rose-400 shrink-0">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-bold text-slate-100 mb-1">Delete Monitor Target</h2>
              <p className="text-sm text-slate-300">
                Are you sure you want to delete <span className="font-semibold text-white">"{target.name}"</span>?
              </p>
            </div>
          </div>

          <div className="mt-4 p-3 bg-slate-950/60 border border-slate-800/80 rounded-lg">
            <div className="text-xs text-slate-500 mb-1">Monitored URL:</div>
            <div className="text-xs font-mono text-slate-300 break-all">{target.url}</div>
          </div>

          <p className="text-xs text-slate-400 mt-4 leading-relaxed">
            This target will be removed from active monitoring and scheduled checks will stop immediately.
          </p>

          {deleteError && (
            <div
              className="mt-4 bg-rose-950/40 border border-rose-800/50 text-rose-300 rounded-lg px-4 py-3 text-sm flex gap-2"
              role="alert"
            >
              <svg className="h-5 w-5 shrink-0 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <span>{deleteError}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-800/80 bg-slate-900/60">
          <button
            type="button"
            onClick={onClose}
            disabled={isDeleting}
            className="px-4 py-2 rounded-lg text-sm font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 transition-all disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            id="confirm-delete-target-btn"
            type="button"
            onClick={handleConfirmDelete}
            disabled={isDeleting}
            className="bg-rose-600 hover:bg-rose-500 active:bg-rose-700 text-white text-sm font-semibold rounded-lg px-5 py-2 transition-all duration-200 shadow-md shadow-rose-950/30 flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {isDeleting ? (
              <>
                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Deleting...
              </>
            ) : (
              'Delete Target'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
