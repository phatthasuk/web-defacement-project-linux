import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  usePaginatedTargetsQuery,
  useCreateTargetMutation,
  useUpdateTargetMutation,
  useDeleteTargetMutation,
  useTriggerCheckMutation,
} from '../hooks/useTargets';
import { TargetStatusBadge } from '../components/TargetStatusBadge';
import { EditTargetModal } from '../components/EditTargetModal';
import { DeleteTargetModal } from '../components/DeleteTargetModal';
import { Target } from '../types/target';
import { ApiError } from '../api/client';
import { formatDateTime } from '../utils/date';
import { TagBadge } from '../components/TagBadge';
import { TagMultiSelect } from '../components/TagMultiSelect';
import { TagFilterModal } from '../components/TagFilterModal';
import { useTagsQuery } from '../hooks/useTags';
import { ScreenshotPreviewModal } from '../components/ScreenshotPreviewModal';
import { useAuth } from '../hooks/authContext';

export function TargetListPage() {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [triggerNotice, setTriggerNotice] = useState<Record<string, string | null>>({});
  const [editingTarget, setEditingTarget] = useState<Target | null>(null);
  const [deletingTarget, setDeletingTarget] = useState<Target | null>(null);
  const [previewTarget, setPreviewTarget] = useState<Target | null>(null);
  const previewTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [newTargetTagIds, setNewTargetTagIds] = useState<string[]>([]);
  const [filteringTagParentId, setFilteringTagParentId] = useState<string | null>(null);
  const tagFilterTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [page, setPage] = useState(1);
  const pageSize = 50;
  const offset = (page - 1) * pageSize;

  const tagIdsFromUrl = searchParams.getAll('tag_ids');
  const tagMatchFromUrl = searchParams.get('tag_match') === 'all' ? 'all' : 'any';
  const activeTagIds = tagIdsFromUrl;
  const activeTagMatch = tagMatchFromUrl;
  const activeStatus = searchParams.get('status') ?? '';
  const sortValue = searchParams.get('sort_by');
  const sortBy = sortValue === 'status' || sortValue === 'last_activity' ? sortValue : undefined;
  const sortOrder = searchParams.get('sort_order') === 'asc' ? 'asc' : 'desc';
  useEffect(() => {
    const timeoutId = window.setTimeout(() => setDebouncedSearchQuery(searchQuery), 300);
    return () => window.clearTimeout(timeoutId);
  }, [searchQuery]);

  const { data: paginatedData, isLoading, isPlaceholderData, isError, error } = usePaginatedTargetsQuery(
    pageSize,
    offset,
    false,
    activeTagIds,
    activeTagMatch,
    activeStatus || undefined,
    sortBy,
    sortOrder,
    debouncedSearchQuery,
  );
  const { data: tagData } = useTagsQuery();
  const availableTags = tagData?.items ?? [];
  const filteringTagParent = availableTags.find((tag) => tag.id === filteringTagParentId && !tag.parent_id) ?? null;
  const filteringTagChildren = filteringTagParent
    ? availableTags.filter((tag) => tag.parent_id === filteringTagParent.id)
    : [];
  const targets = paginatedData?.items;
  const total = paginatedData?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const createTargetMutation = useCreateTargetMutation();
  const updateTargetMutation = useUpdateTargetMutation();
  const deleteTargetMutation = useDeleteTargetMutation();
  const triggerCheckMutation = useTriggerCheckMutation();

  const handleAddTarget = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    
    if (!name.trim() || !url.trim()) {
      setFormError('Name and URL are required.');
      return;
    }

    try {
      await createTargetMutation.mutateAsync({
        name: name.trim(),
        url: url.trim(),
        ...(newTargetTagIds.length ? { tag_ids: newTargetTagIds } : {}),
      });
      setName('');
      setUrl('');
      setNewTargetTagIds([]);
      setPage(1);
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.detail);
      } else {
        setFormError('Failed to add target. Please try again.');
      }
    }
  };

  const handleRunCheck = async (targetId: string) => {
    setTriggerNotice((prev) => ({ ...prev, [targetId]: null }));
    try {
      const res = await triggerCheckMutation.mutateAsync(targetId);
      if (res.accepted === false) {
        setTriggerNotice((prev) => ({ ...prev, [targetId]: 'Check already in progress.' }));
        setTimeout(() => {
          setTriggerNotice((prev) => ({ ...prev, [targetId]: null }));
        }, 5000);
      }
    } catch (err) {
      console.error('Failed to trigger check:', err);
      const msg = err instanceof ApiError ? err.detail : 'Failed to start check.';
      setTriggerNotice((prev) => ({ ...prev, [targetId]: msg }));
      setTimeout(() => {
        setTriggerNotice((prev) => ({ ...prev, [targetId]: null }));
      }, 5000);
    }
  };

  const handleSaveEdit = async (targetId: string, newName: string, newUrl: string, tagIds: string[]) => {
    await updateTargetMutation.mutateAsync({
      targetId,
      payload: { name: newName, url: newUrl, tag_ids: tagIds },
    });
  };

  const applyTagFilter = (tagIds: string[], match = activeTagMatch) => {
    const params = new URLSearchParams(searchParams);
    params.delete('tag_ids');
    params.delete('tag_match');
    tagIds.forEach((tagId) => params.append('tag_ids', tagId));
    if (tagIds.length) params.set('tag_match', match);
    else params.delete('tag_match');
    setSearchParams(params);
    setPage(1);
  };

  const closeTagFilter = () => {
    setFilteringTagParentId(null);
    requestAnimationFrame(() => tagFilterTriggerRef.current?.focus());
  };

  const applyTagGroupFilter = (groupIds: string[]) => {
    if (!filteringTagParent) return;
    const currentGroupIds = new Set([filteringTagParent.id, ...filteringTagChildren.map((tag) => tag.id)]);
    const nextTagIds = [
      ...activeTagIds.filter((tagId) => !currentGroupIds.has(tagId)),
      ...groupIds.filter((tagId) => currentGroupIds.has(tagId)),
    ];
    applyTagFilter(nextTagIds);
    closeTagFilter();
  };

  const applyStatusFilter = (status: string) => {
    const params = new URLSearchParams(searchParams);
    if (status) params.set('status', status);
    else params.delete('status');
    setSearchParams(params);
    setPage(1);
  };

  const toggleSort = (column: 'status' | 'last_activity') => {
    const nextOrder = sortBy === column && sortOrder === 'desc' ? 'asc' : 'desc';
    const params = new URLSearchParams(searchParams);
    params.set('sort_by', column);
    params.set('sort_order', nextOrder);
    setSearchParams(params);
    setPage(1);
  };

  const sortButton = (column: 'status' | 'last_activity', label: string) => {
    const selected = sortBy === column;
    const direction = selected ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none';
    return (
      <button type="button" onClick={() => toggleSort(column)} aria-label={`Sort by ${label}${selected ? `, ${direction}` : ''}`} title={column === 'status' ? 'Changed targets are ordered by structural score' : 'Order by last activity time'} className="inline-flex items-center gap-1.5 hover:text-slate-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500 rounded">
        {label}
        <span aria-hidden="true" className={selected ? 'text-cyan-400' : 'text-slate-600'}>{selected ? (sortOrder === 'asc' ? '↑' : '↓') : '↕'}</span>
      </button>
    );
  };

  const handleConfirmDelete = async (targetId: string) => {
    await deleteTargetMutation.mutateAsync(targetId);
    if (page > 1 && targets && targets.length <= 1) {
      setPage((prev) => Math.max(1, prev - 1));
    }
  };

  const formatLastActivity = (isoString: string) => {
    return formatDateTime(isoString, {
      dateStyle: 'short',
      timeStyle: 'medium',
    });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <header className="mb-10 text-center md:text-left">
        <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-cyan-400 via-indigo-400 to-purple-500 bg-clip-text text-transparent">
          Web Defacement Monitor
        </h1>
        <p className="text-slate-400 mt-2">
          Monitor your websites for unexpected visual and content alterations in real time.
        </p>
      </header>

      <div className="flex flex-col lg:flex-row items-start gap-8">
        {/* Left column: Add Target Form */}
        {isAdmin && <div className="w-full lg:w-80 xl:w-96 shrink-0">
          <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-xl shadow-xl">
            <h2 className="text-xl font-semibold text-slate-200 mb-6">Add New Monitor</h2>
            <form onSubmit={handleAddTarget} className="space-y-5">
              <div>
                <label htmlFor="name-input" className="block text-sm font-medium text-slate-400 mb-2">
                  Target Name
                </label>
                <input
                  id="name-input"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Production Gateway"
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-4 py-2.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500 transition-all"
                  disabled={createTargetMutation.isPending}
                />
              </div>

              <TagMultiSelect
                tags={availableTags}
                selectedIds={newTargetTagIds}
                onChange={setNewTargetTagIds}
                disabled={createTargetMutation.isPending}
              />

              <div>
                <label htmlFor="url-input" className="block text-sm font-medium text-slate-400 mb-2">
                  Target URL
                </label>
                <input
                  id="url-input"
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com"
                  className="w-full bg-slate-950/80 border border-slate-800 rounded-lg px-4 py-2.5 text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500 transition-all"
                  disabled={createTargetMutation.isPending}
                />
              </div>

              {formError && (
                <div className="bg-rose-950/40 border border-rose-800/50 text-rose-300 rounded-lg px-4 py-3 text-sm flex gap-2" role="alert">
                  <svg className="h-5 w-5 shrink-0 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <span>{formError}</span>
                </div>
              )}

              <button
                id="add-target-submit"
                type="submit"
                className="w-full bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-white font-semibold rounded-lg px-4 py-2.5 transition-all duration-300 transform active:scale-[0.98] shadow-md shadow-cyan-950/30 flex items-center justify-center gap-2"
                disabled={createTargetMutation.isPending}
              >
                {createTargetMutation.isPending ? (
                  <>
                    <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Adding...
                  </>
                ) : (
                  'Add Target'
                )}
              </button>
            </form>
          </div>
        </div>}

        {/* Right column: Target List */}
        <div className="flex-1 w-full min-w-0">
          <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl backdrop-blur-xl shadow-xl overflow-hidden">
            <div className="px-6 py-5 border-b border-slate-800/80 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-200">Monitored Targets</h2>
              {paginatedData && (
                <span className="text-xs font-semibold text-slate-500 bg-slate-950 px-2.5 py-1 rounded-full border border-slate-800">
                  {total} {total === 1 ? 'Target' : 'Targets'}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-3 border-b border-slate-800/80 px-6 py-4">
              <div className="relative w-full max-w-sm">
                <input aria-label="Search websites" placeholder="Search by website name or URL" value={searchQuery} onChange={event => { setSearchQuery(event.target.value); setPage(1); }} className="w-full rounded-lg border border-slate-800 bg-slate-950 py-2 pl-3 pr-28 text-sm text-slate-200 placeholder:text-slate-600" />
                {searchQuery !== debouncedSearchQuery && (
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500" role="status" aria-live="polite">Searching…</span>
                )}
                {searchQuery === debouncedSearchQuery && isPlaceholderData && (
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-slate-500" role="status" aria-live="polite">Updating…</span>
                )}
              </div>
              <div className="flex items-start justify-between gap-4">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Filter tags</span>
                  {availableTags.filter((tag) => !tag.parent_id).map((tag) => {
                    const children = availableTags.filter((child) => child.parent_id === tag.id);
                    const selectedChildCount = children.filter((child) => activeTagIds.includes(child.id)).length;
                    const selected = activeTagIds.includes(tag.id) || selectedChildCount > 0;
                    return (
                      <button
                        key={tag.id}
                        type="button"
                        aria-label={`${tag.name}${selectedChildCount ? `, ${selectedChildCount} sub-tags selected` : ''}. Open tag filter`}
                        aria-haspopup="dialog"
                        onClick={(event) => {
                          tagFilterTriggerRef.current = event.currentTarget;
                          setFilteringTagParentId(tag.id);
                        }}
                        className={`flex items-center gap-1.5 rounded-full transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 ${selected ? 'opacity-100 ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-900' : 'opacity-60 hover:opacity-100'}`}
                      >
                        <TagBadge tag={tag} />
                        {selectedChildCount > 0 && <span className="pr-1 text-[10px] text-slate-300">+{selectedChildCount}</span>}
                      </button>
                    );
                  })}
                  {activeTagIds.length > 0 && (
                    <>
                      <select aria-label="Tag filter mode" value={activeTagMatch} onChange={(event) => applyTagFilter(activeTagIds, event.target.value as 'any' | 'all')} className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-300 focus:outline-none">
                        <option value="any">Match any</option>
                        <option value="all">Match all</option>
                      </select>
                      <button type="button" onClick={() => applyTagFilter([])} className="text-xs font-medium text-cyan-400 hover:text-cyan-300">Clear</button>
                    </>
                  )}
                </div>
                <label className="flex shrink-0 items-center gap-2 pt-1 text-xs text-slate-400">
                  <span>Status</span>
                  <select aria-label="Filter by status" value={activeStatus} onChange={(event) => applyStatusFilter(event.target.value)} className="rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-2 focus:ring-cyan-500/50">
                    <option value="">All statuses</option>
                    <option value="Changed">Changed</option>
                    <option value="Defaced">Defaced</option>
                    <option value="Failed">Failed</option>
                    <option value="Availability Issue">Availability Issue</option>
                    <option value="Acknowledged">Acknowledged</option>
                    <option value="Awaiting Baseline">Awaiting Baseline</option>
                    <option value="Checking">Checking</option>
                    <option value="OK">OK</option>
                    <option value="Never Checked">Never Checked</option>
                  </select>
                </label>
              </div>
            </div>

            {isLoading ? (
              <div className="flex flex-col items-center justify-center py-20 gap-4">
                <svg className="animate-spin h-8 w-8 text-cyan-500" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <p className="text-slate-500 text-sm">Loading monitoring targets...</p>
              </div>
            ) : isError ? (
              <div className="p-8 text-center text-rose-400">
                <p>Failed to load targets.</p>
                <p className="text-sm text-slate-500 mt-1">
                  {error instanceof ApiError ? error.detail : error?.message}
                </p>
              </div>
            ) : !targets || targets.length === 0 ? (
              <div className="py-20 px-6 text-center">
                <svg className="mx-auto h-12 w-12 text-slate-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <h3 className="text-slate-300 font-medium text-lg mb-1">{activeTagIds.length || activeStatus || searchQuery ? 'No targets match the selected filters' : isAdmin ? 'No targets configured' : 'No websites assigned'}</h3>
                <p className="text-slate-500 text-sm max-w-sm mx-auto">
                  {activeTagIds.length || activeStatus || searchQuery ? 'Try changing or clearing the selected filters.' : isAdmin ? 'Add a new target website on the left to start tracking content and visual adjustments.' : 'An Admin must assign websites to your account before they appear here.'}
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full table-fixed text-left border-collapse">
                  <colgroup>
                    <col className="w-[48%]" />
                    <col className="w-[26%]" />
                    <col className="w-[26%]" />
                  </colgroup>
                  <thead>
                    <tr className="border-b border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      <th className="px-6 py-4">Target / URL</th>
                      <th aria-sort={sortBy === 'status' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'} className="px-6 py-4 whitespace-nowrap">{sortButton('status', 'Status')}</th>
                      <th aria-sort={sortBy === 'last_activity' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'} className="px-4 py-4 whitespace-nowrap">{sortButton('last_activity', 'Last Activity')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {targets.map((target) => (
                      <tr key={target.id} className="hover:bg-slate-900/20 transition-colors group">
                        <td className="px-6 py-4">
                          <Link
                            to={`/targets/${target.id}`}
                            className="font-semibold text-slate-200 hover:text-cyan-400 group-hover:text-cyan-300 transition-colors"
                          >
                            {target.name}
                          </Link>
                          <a
                            href={target.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-slate-500 hover:text-cyan-400 font-mono transition-colors block mt-0.5 break-all"
                          >
                            {target.url}
                          </a>
                          {(target.tags?.length ?? 0) > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {(target.tags ?? []).map((tag) => <TagBadge key={tag.id} tag={tag} />)}
                            </div>
                          )}
                          {isAdmin && (target.assignees?.length ?? 0) > 0 && <p className="mt-2 text-xs text-slate-500">Assigned: {target.assignees?.map(a => `${a.display_name}${a.is_active ? '' : ' (suspended)'}`).join(', ')}</p>}
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            <button
                              data-testid={`run-check-${target.id}`}
                              onClick={() => handleRunCheck(target.id)}
                              disabled={target.status === 'Checking' || (triggerCheckMutation.isPending && triggerCheckMutation.variables === target.id)}
                              className="whitespace-nowrap px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-slate-800 hover:border-slate-600 hover:text-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                            >
                              {target.status === 'Checking' || (triggerCheckMutation.isPending && triggerCheckMutation.variables === target.id) ? 'Checking...' : 'Run Check'}
                            </button>
                            <button
                              type="button"
                              data-testid={`preview-target-${target.id}`}
                              aria-label={`Preview screenshot comparison for ${target.name}`}
                              aria-haspopup="dialog"
                              onClick={(event) => {
                                previewTriggerRef.current = event.currentTarget;
                                setPreviewTarget(target);
                              }}
                              title="Preview screenshot comparison"
                              className="whitespace-nowrap px-2 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-slate-800 hover:border-cyan-500/50 hover:text-cyan-300 transition-all flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M2.25 12s3.5-6.5 9.75-6.5 9.75 6.5 9.75 6.5-3.5 6.5-9.75 6.5S2.25 12 2.25 12z" />
                                <circle cx="12" cy="12" r="2.75" strokeWidth={1.8} />
                              </svg>
                              Preview
                            </button>
                            {isAdmin && <button
                              data-testid={`edit-target-${target.id}`}
                              onClick={() => setEditingTarget(target)}
                              className="whitespace-nowrap px-2 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-slate-800 hover:border-cyan-500/50 hover:text-cyan-300 transition-all flex items-center gap-1.5"
                              title="Edit Target"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                              </svg>
                              Edit
                            </button>}
                            {isAdmin && <button
                              data-testid={`delete-target-${target.id}`}
                              onClick={() => setDeletingTarget(target)}
                              className="whitespace-nowrap px-2 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-rose-950/40 hover:border-rose-700/60 hover:text-rose-400 transition-all flex items-center gap-1.5"
                              title="Delete Target"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                              Delete
                            </button>}
                          </div>
                          {(target.status === 'Failed' || target.status === 'Availability Issue') && target.last_error && (
                            <span className="text-xs text-rose-400 block mt-1 max-w-md truncate" title={target.last_error}>
                              {target.status}: {target.last_error}
                            </span>
                          )}
                          {triggerNotice[target.id] && (
                            <span className="text-xs text-amber-400 block mt-1 max-w-md truncate" title={triggerNotice[target.id] || undefined}>
                              Notice: {triggerNotice[target.id]}
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <TargetStatusBadge
                            status={target.status}
                            title={target.last_error || undefined}
                          />
                          {target.check_run_id && target.next_check_at && target.status !== 'Checking' && (
                            <span className="mt-1 block text-xs text-amber-400" title={target.last_error || undefined}>
                              Retry {Math.min((target.check_attempt_count ?? 0) + 1, target.check_retry_max_attempts ?? 3)}/{target.check_retry_max_attempts ?? 3} · {formatDateTime(target.next_check_at)}
                            </span>
                          )}
                          {!target.check_run_id && target.next_check_at && (
                            <span className="mt-1 block text-xs text-slate-500">
                              Next check · {formatDateTime(target.next_check_at)}
                            </span>
                          )}
                          {target.status === 'Changed' && (
                            <span className="mt-1 block text-xs text-slate-500">
                              Structural Score:{' '}
                              <span className="font-mono font-semibold text-amber-400">
                                {target.latest_structure_change_score == null
                                  ? '—'
                                  : `${(target.latest_structure_change_score * 100).toFixed(1)}%`}
                              </span>
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-4 text-xs text-slate-400 font-mono whitespace-nowrap">
                          {formatLastActivity(target.updated_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {total > 0 && (
              <div className="px-6 py-4 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-3 text-sm text-slate-400">
                <div className="text-xs">
                  Showing {Math.min(offset + 1, total)}–{Math.min(offset + (targets?.length ?? 0), total)} of {total} targets
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-950 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs font-medium"
                  >
                    Previous
                  </button>
                  <span className="text-xs text-slate-400 font-medium px-1">
                    Page {page} of {totalPages}
                  </span>
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                    className="px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-950 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs font-medium"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <EditTargetModal
        isOpen={!!editingTarget}
        target={editingTarget}
        onClose={() => setEditingTarget(null)}
        onSave={handleSaveEdit}
        isSaving={updateTargetMutation.isPending}
        availableTags={availableTags}
      />

      <DeleteTargetModal
        isOpen={!!deletingTarget}
        target={deletingTarget}
        onClose={() => setDeletingTarget(null)}
        onConfirm={handleConfirmDelete}
        isDeleting={deleteTargetMutation.isPending}
      />

      {previewTarget && (
        <ScreenshotPreviewModal
          target={previewTarget}
          onClose={() => {
            setPreviewTarget(null);
            requestAnimationFrame(() => previewTriggerRef.current?.focus());
          }}
        />
      )}

      {filteringTagParent && (
        <TagFilterModal
          parent={filteringTagParent}
          children={filteringTagChildren}
          selectedIds={activeTagIds}
          onApply={applyTagGroupFilter}
          onClose={closeTagFilter}
        />
      )}
    </div>
  );
}
