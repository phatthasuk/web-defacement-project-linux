import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { TagBadge } from './TagBadge';
import type { Tag } from '../types/tag';

interface TagMultiSelectProps {
  tags: Tag[];
  selectedIds: string[];
  onChange: (tagIds: string[]) => void;
  disabled?: boolean;
  label?: string;
}

export function TagMultiSelect({ tags, selectedIds, onChange, disabled = false, label = 'Tags' }: TagMultiSelectProps) {
  const [activeParentId, setActiveParentId] = useState<string | null>(null);
  const [draftIds, setDraftIds] = useState<string[]>([]);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const roots = useMemo(() => tags.filter((tag) => !tag.parent_id), [tags]);
  const activeParent = roots.find((tag) => tag.id === activeParentId) ?? null;
  const children = activeParent ? tags.filter((tag) => tag.parent_id === activeParent.id) : [];
  const selected = new Set(selectedIds);

  useEffect(() => {
    if (activeParentId) closeButtonRef.current?.focus();
  }, [activeParentId]);

  const openPicker = (parentId: string, trigger: HTMLButtonElement) => {
    triggerRef.current = trigger;
    setDraftIds(selectedIds);
    setActiveParentId(parentId);
  };

  const closePicker = () => {
    setActiveParentId(null);
    requestAnimationFrame(() => triggerRef.current?.focus());
  };

  const toggleDraft = (tagId: string) => {
    setDraftIds((current) => current.includes(tagId)
      ? current.filter((id) => id !== tagId)
      : [...current, tagId]);
  };

  const handleDialogKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      closePicker();
      return;
    }

    if (event.key !== 'Tab') return;
    const focusable = event.currentTarget.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), a[href]'
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
    <fieldset disabled={disabled}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <legend className="text-sm font-medium text-slate-300">{label}</legend>
        <Link to="/tags" className="text-xs font-medium text-cyan-400 hover:text-cyan-300">Manage Tags</Link>
      </div>
      {tags.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-700 px-3 py-2 text-xs text-slate-500">
          No tags yet. Create one in Manage Tags.
        </p>
      ) : (
        <div className="flex min-h-12 flex-wrap gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-2">
          {roots.map((parent) => {
            const childCount = tags.filter((tag) => tag.parent_id === parent.id && selected.has(tag.id)).length;
            const parentSelected = selected.has(parent.id);
            const hasSelection = parentSelected || childCount > 0;
            return (
              <button
                key={parent.id}
                type="button"
                aria-label={`${parent.name}${childCount ? `, ${childCount} sub-tags selected` : ''}. Open tag options`}
                aria-haspopup="dialog"
                onClick={(event) => openPicker(parent.id, event.currentTarget)}
                className={`flex items-center gap-1.5 rounded-full transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 ${hasSelection ? 'opacity-100' : 'opacity-55 hover:opacity-100'}`}
              >
                <TagBadge tag={parent} />
                {childCount > 0 && <span className="pr-1 text-[10px] text-slate-300">+{childCount}</span>}
              </button>
            );
          })}
        </div>
      )}

      {activeParent && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/75 p-4 backdrop-blur-sm"
          onClick={closePicker}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="tag-picker-title"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={handleDialogKeyDown}
            className="w-full max-w-md overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"
          >
            <header className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
              <div>
                <h2 id="tag-picker-title" className="text-base font-semibold text-slate-100">Choose tags</h2>
                <div className="mt-1"><TagBadge tag={activeParent} /></div>
              </div>
              <button
                ref={closeButtonRef}
                type="button"
                onClick={closePicker}
                aria-label="Close tag options"
                className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </header>

            <div className="max-h-[60vh] space-y-4 overflow-y-auto p-5">
              <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                <input
                  type="checkbox"
                  checked={draftIds.includes(activeParent.id)}
                  onChange={() => toggleDraft(activeParent.id)}
                  className="h-4 w-4 accent-cyan-400"
                />
                <span className="text-sm text-slate-200">Select parent tag</span>
              </label>

              {children.length > 0 ? (
                <fieldset className="space-y-2">
                  <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Sub Tags</legend>
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

            <footer className="flex justify-end gap-2 border-t border-slate-800 px-5 py-4">
              <button type="button" onClick={closePicker} className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition hover:bg-slate-800">
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  onChange(draftIds);
                  closePicker();
                }}
                className="rounded-lg bg-gradient-to-r from-cyan-500 to-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:from-cyan-400 hover:to-indigo-500"
              >
                Apply
              </button>
            </footer>
          </div>
        </div>
      )}
    </fieldset>
  );
}
