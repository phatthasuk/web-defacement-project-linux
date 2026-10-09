import { useCallback, useEffect, useState } from 'react';
import { ApiError } from '../api/client';
import { useRemoveTagFromTargetMutation, useTagTargetsQuery } from '../hooks/useTags';
import type { Tag } from '../types/tag';
import { TagBadge } from './TagBadge';

const PAGE_SIZE = 20;

interface TagWebsitesModalProps {
  tag: Tag | null;
  onClose: () => void;
}

export function TagWebsitesModal({ tag, onClose }: TagWebsitesModalProps) {
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const targetsQuery = useTagTargetsQuery(tag?.id ?? '', PAGE_SIZE, offset);
  const removeMutation = useRemoveTagFromTargetMutation();
  const isRemoving = removeMutation.isPending;

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (event.key === 'Escape' && !isRemoving) onClose();
  }, [isRemoving, onClose]);

  useEffect(() => {
    if (!tag) return;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [tag, handleKeyDown]);

  if (!tag) return null;

  const targets = targetsQuery.data?.items ?? [];
  const total = targetsQuery.data?.total ?? 0;
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + PAGE_SIZE, total);

  const removeTag = async (targetId: string) => {
    setError(null);
    try {
      await removeMutation.mutateAsync({ targetId, tagId: tag.id });
      if (targets.length === 1 && offset > 0) setOffset(Math.max(0, offset - PAGE_SIZE));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : 'Unable to remove this tag from the website.');
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="tag-websites-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
      onClick={() => { if (!isRemoving) onClose(); }}
    >
      <section
        className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-800 px-6 py-5">
          <div className="min-w-0">
            <h2 id="tag-websites-title" className="text-lg font-semibold text-slate-100">Websites with this tag</h2>
            <div className="mt-2 flex items-center gap-2">
              <TagBadge tag={tag} />
              <span className="text-sm text-slate-400">{total} active website{total === 1 ? '' : 's'}</span>
            </div>
          </div>
          <button type="button" onClick={onClose} disabled={isRemoving} autoFocus aria-label="Close" className="rounded-lg px-2 py-1 text-xl leading-none text-slate-400 hover:bg-slate-800 hover:text-white disabled:opacity-50">×</button>
        </header>

        <div className="min-h-36 overflow-y-auto">
          {targetsQuery.isLoading ? (
            <p className="p-8 text-center text-sm text-slate-400">Loading websites…</p>
          ) : targetsQuery.isError ? (
            <div className="p-8 text-center">
              <p role="alert" className="text-sm text-rose-300">{targetsQuery.error instanceof ApiError ? targetsQuery.error.detail : 'Unable to load websites.'}</p>
              <button type="button" onClick={() => void targetsQuery.refetch()} className="mt-3 text-sm font-medium text-cyan-400 hover:text-cyan-300">Try again</button>
            </div>
          ) : targets.length === 0 ? (
            <p className="p-8 text-center text-sm text-slate-400">No active websites have this tag.</p>
          ) : (
            <ul className="divide-y divide-slate-800/70">
              {targets.map((target) => (
                <li key={target.id} className="flex items-center gap-4 px-6 py-4">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-200">{target.name}</p>
                    <p className="truncate text-xs text-slate-500" title={target.url}>{target.url}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void removeTag(target.id)}
                    disabled={isRemoving}
                    className="shrink-0 rounded-lg border border-rose-800/60 px-3 py-1.5 text-sm font-medium text-rose-300 hover:bg-rose-950/50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {removeMutation.variables?.targetId === target.id && isRemoving ? 'Removing…' : 'Untag'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && <p role="alert" className="border-t border-rose-900/60 bg-rose-950/30 px-6 py-3 text-sm text-rose-300">{error}</p>}

        {total > PAGE_SIZE && !targetsQuery.isError && (
          <footer className="flex items-center justify-between border-t border-slate-800 px-6 py-3">
            <span className="text-xs text-slate-500">Showing {start}–{end} of {total}</span>
            <div className="flex gap-2">
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="rounded-lg bg-slate-800 px-3 py-1.5 text-sm text-slate-300 disabled:opacity-40">Previous</button>
              <button type="button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)} className="rounded-lg bg-slate-800 px-3 py-1.5 text-sm text-slate-300 disabled:opacity-40">Next</button>
            </div>
          </footer>
        )}
      </section>
    </div>
  );
}
