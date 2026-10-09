import { FormEvent, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import { TagBadge } from '../components/TagBadge';
import { TagWebsitesModal } from '../components/TagWebsitesModal';
import { useCreateTagMutation, useDeleteTagMutation, useTagsQuery, useUpdateTagMutation } from '../hooks/useTags';
import type { Tag, TagColor } from '../types/tag';

const colors: TagColor[] = ['cyan', 'blue', 'violet', 'emerald', 'amber', 'rose', 'slate'];

export function TagsPage() {
  const [name, setName] = useState('');
  const [colorKey, setColorKey] = useState<TagColor>('cyan');
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Tag | null>(null);
  const [viewingTag, setViewingTag] = useState<Tag | null>(null);
  const returnFocusRef = useRef<HTMLButtonElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data, isLoading, isError, error: loadError } = useTagsQuery(search);
  const createMutation = useCreateTagMutation();
  const updateMutation = useUpdateTagMutation();
  const deleteMutation = useDeleteTagMutation();

  useEffect(() => {
    if (!viewingTag) returnFocusRef.current?.focus();
  }, [viewingTag]);

  const resetForm = () => {
    setName('');
    setColorKey('cyan');
    setEditing(null);
    setError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError('Tag name is required.');
      return;
    }
    setError(null);
    try {
      if (editing) {
        await updateMutation.mutateAsync({ tagId: editing.id, payload: { name: trimmedName, color_key: colorKey } });
      } else {
        await createMutation.mutateAsync({ name: trimmedName, color_key: colorKey });
      }
      resetForm();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : 'Unable to save this tag.');
    }
  };

  const startEdit = (tag: Tag) => {
    setEditing(tag);
    setName(tag.name);
    setColorKey(tag.color_key);
    setError(null);
  };

  const remove = async (tag: Tag) => {
    if (!window.confirm(`Delete “${tag.name}”? It will be removed from ${tag.target_count} active website${tag.target_count === 1 ? '' : 's'}.`)) return;
    try {
      await deleteMutation.mutateAsync(tag.id);
      if (editing?.id === tag.id) resetForm();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.detail : 'Unable to delete this tag.');
    }
  };

  const preview = { name: name.trim() || 'Tag preview', color_key: colorKey };
  const saving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8">
        <h1 className="text-3xl font-extrabold text-slate-100">Tags Management</h1>
        <p className="mt-2 text-slate-400">Create shared labels to group and filter monitored websites.</p>
      </header>

      <div className="grid items-start gap-8 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <section className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-6 shadow-xl">
          <h2 className="text-xl font-semibold text-slate-200">{editing ? 'Edit Tag' : 'Add Tag'}</h2>
          <form onSubmit={submit} className="mt-6 space-y-5">
            <div>
              <label htmlFor="tag-name" className="mb-2 block text-sm font-medium text-slate-300">Tag name</label>
              <input id="tag-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={50} disabled={saving}
                placeholder="e.g. Production" className="w-full rounded-lg border border-slate-800 bg-slate-950/80 px-4 py-2.5 text-slate-200 placeholder-slate-600 focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/50" />
            </div>
            <fieldset disabled={saving}>
              <legend className="mb-2 text-sm font-medium text-slate-300">Color</legend>
              <div className="flex flex-wrap gap-2">
                {colors.map((color) => (
                  <label key={color} className="cursor-pointer">
                    <input type="radio" name="tag-color" value={color} checked={colorKey === color} onChange={() => setColorKey(color)} className="peer sr-only" />
                    <span className="block rounded-lg border border-transparent p-1 peer-checked:border-cyan-300 peer-focus-visible:ring-2 peer-focus-visible:ring-cyan-400"><TagBadge tag={{ name: color, color_key: color }} /></span>
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-500">
              Preview <span className="ml-2"><TagBadge tag={preview} /></span>
            </div>
            {error && <p role="alert" className="rounded-lg border border-rose-800/50 bg-rose-950/40 px-3 py-2 text-sm text-rose-300">{error}</p>}
            <div className="flex gap-3">
              <button type="submit" disabled={saving} className="rounded-lg bg-gradient-to-r from-cyan-500 to-indigo-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">
                {saving ? 'Saving…' : editing ? 'Save changes' : 'Add Tag'}
              </button>
              {editing && <button type="button" onClick={resetForm} disabled={saving} className="rounded-lg bg-slate-800 px-4 py-2.5 text-sm font-semibold text-slate-300">Cancel</button>}
            </div>
          </form>
        </section>

        <section className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/40 shadow-xl">
          <div className="flex flex-col gap-4 border-b border-slate-800/80 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
            <div><h2 className="text-xl font-semibold text-slate-200">Tags</h2><p className="mt-1 text-xs text-slate-500">{data?.total ?? 0} tags</p></div>
            <input aria-label="Search tags" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tags" className="rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-500 focus:outline-none" />
          </div>
          {isLoading ? <p className="p-8 text-sm text-slate-500">Loading tags…</p> : isError ? <p className="p-8 text-sm text-rose-300">{loadError instanceof ApiError ? loadError.detail : 'Unable to load tags.'}</p> : data?.items.length === 0 ? <p className="p-8 text-sm text-slate-500">No tags match this search.</p> :
            <ul className="divide-y divide-slate-800/60">{data?.items.map((tag) => <li key={tag.id} className="flex items-center gap-4 px-6 py-4"><TagBadge tag={tag} /><button type="button" onClick={(event) => { returnFocusRef.current = event.currentTarget; setViewingTag(tag); }} aria-label={`View ${tag.target_count} websites with ${tag.name} tag`} className="min-w-0 flex-1 text-left text-sm text-slate-400 hover:text-cyan-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500">{tag.target_count} active website{tag.target_count === 1 ? '' : 's'}</button><button type="button" onClick={() => startEdit(tag)} className="text-sm font-medium text-cyan-400 hover:text-cyan-300">Edit</button><button type="button" onClick={() => remove(tag)} disabled={deleteMutation.isPending} className="text-sm font-medium text-rose-400 hover:text-rose-300 disabled:opacity-50">Delete</button></li>)}</ul>}
        </section>
      </div>
      {viewingTag && <TagWebsitesModal key={viewingTag.id} tag={viewingTag} onClose={() => setViewingTag(null)} />}
    </div>
  );
}
