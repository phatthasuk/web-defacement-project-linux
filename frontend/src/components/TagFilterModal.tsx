import { useEffect, useRef, useState } from 'react';
import { TagBadge } from './TagBadge';
import type { Tag } from '../types/tag';

interface TagFilterModalProps {
  parent: Tag;
  children: Tag[];
  selectedIds: string[];
  onApply: (selectedIds: string[]) => void;
  onClose: () => void;
}

export function TagFilterModal({ parent, children, selectedIds, onApply, onClose }: TagFilterModalProps) {
  const [draftIds, setDraftIds] = useState(selectedIds);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const titleId = `tag-filter-title-${parent.id}`;

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);

  const toggleDraft = (tagId: string) => {
    setDraftIds((current) => current.includes(tagId)
      ? current.filter((id) => id !== tagId)
      : [...current, tagId]);
  };

  const handleDialogKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
      return;
    }

    if (event.key !== 'Tab') return;
    const focusable = event.currentTarget.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled)'
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
      className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
        onKeyDown={handleDialogKeyDown}
        className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-slate-100">Filter by tags</h2>
            <div className="mt-1"><TagBadge tag={parent} /></div>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close tag filter"
            className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="max-h-[60vh] space-y-4 overflow-y-auto p-5">
          <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
            <input
              type="checkbox"
              checked={draftIds.includes(parent.id)}
              onChange={() => toggleDraft(parent.id)}
              className="h-4 w-4 accent-cyan-400"
            />
            <span className="text-sm text-slate-200">Select parent tag</span>
          </label>

          {children.length > 0 ? (
            <fieldset className="space-y-2">
              <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Sub-tags</legend>
              {children.map((tag) => (
                <label key={tag.id} className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3 transition hover:border-slate-700">
                  <input
                    type="checkbox"
                    checked={draftIds.includes(tag.id)}
                    onChange={() => toggleDraft(tag.id)}
                    className="h-4 w-4 accent-cyan-400"
                  />
                  <TagBadge tag={tag} />
                </label>
              ))}
            </fieldset>
          ) : (
            <p className="rounded-lg border border-dashed border-slate-700 px-3 py-4 text-sm text-slate-500">
              This parent tag has no sub-tags yet.
            </p>
          )}
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 px-5 py-4">
          <button
            type="button"
            onClick={() => setDraftIds((current) => current.filter((id) => id !== parent.id && !children.some((child) => child.id === id)))}
            className="rounded-lg px-3 py-2 text-sm font-medium text-slate-400 transition hover:text-slate-200"
          >
            Clear this group
          </button>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition hover:bg-slate-800">
              Cancel
            </button>
            <button
              type="button"
              onClick={() => onApply(draftIds)}
              className="rounded-lg bg-gradient-to-r from-cyan-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:from-cyan-400 hover:to-indigo-500"
            >
              Apply
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
