import { useState } from 'react';
import { Link } from 'react-router-dom';
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

export function TargetListPage() {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [triggerNotice, setTriggerNotice] = useState<Record<string, string | null>>({});
  const [editingTarget, setEditingTarget] = useState<Target | null>(null);
  const [deletingTarget, setDeletingTarget] = useState<Target | null>(null);

  const [page, setPage] = useState(1);
  const pageSize = 50;
  const offset = (page - 1) * pageSize;

  const { data: paginatedData, isLoading, isError, error } = usePaginatedTargetsQuery(pageSize, offset);
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
      await createTargetMutation.mutateAsync({ name: name.trim(), url: url.trim() });
      setName('');
      setUrl('');
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

  const handleSaveEdit = async (targetId: string, newName: string, newUrl: string) => {
    await updateTargetMutation.mutateAsync({
      targetId,
      payload: { name: newName, url: newUrl },
    });
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
        <div className="w-full lg:w-80 xl:w-96 shrink-0">
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
        </div>

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
                <h3 className="text-slate-300 font-medium text-lg mb-1">No targets configured</h3>
                <p className="text-slate-500 text-sm max-w-sm mx-auto">
                  Add a new target website on the left to start tracking content and visual adjustments.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      <th className="px-6 py-4">Target / URL</th>
                      <th className="px-6 py-4 whitespace-nowrap">Status</th>
                      <th className="px-6 py-4 whitespace-nowrap min-w-[190px]">Last Activity</th>
                      <th className="px-6 py-4 text-right whitespace-nowrap">Actions</th>
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
                            className="text-xs text-slate-500 hover:text-cyan-400 font-mono transition-colors block mt-0.5"
                          >
                            {target.url}
                          </a>
                          {target.status === 'Failed' && target.last_error && (
                            <span className="text-xs text-rose-400 block mt-1 max-w-md truncate" title={target.last_error}>
                              Error: {target.last_error}
                            </span>
                          )}
                          {triggerNotice[target.id] && (
                            <span className="text-xs text-amber-400 block mt-1 max-w-md truncate" title={triggerNotice[target.id] || undefined}>
                              Notice: {triggerNotice[target.id]}
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <TargetStatusBadge
                            status={target.status}
                            title={target.status === 'Failed' ? target.last_error || undefined : undefined}
                          />
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-400 font-mono whitespace-nowrap">
                          {formatLastActivity(target.updated_at)}
                        </td>
                        <td className="px-6 py-4 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              data-testid={`run-check-${target.id}`}
                              onClick={() => handleRunCheck(target.id)}
                              disabled={target.status === 'Checking' || (triggerCheckMutation.isPending && triggerCheckMutation.variables === target.id)}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-slate-800 hover:border-slate-600 hover:text-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                            >
                              {target.status === 'Checking' || (triggerCheckMutation.isPending && triggerCheckMutation.variables === target.id) ? 'Checking...' : 'Run Check'}
                            </button>
                            <button
                              data-testid={`edit-target-${target.id}`}
                              onClick={() => setEditingTarget(target)}
                              className="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-slate-800 hover:border-cyan-500/50 hover:text-cyan-300 transition-all flex items-center gap-1.5"
                              title="Edit Target"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                              </svg>
                              Edit
                            </button>
                            <button
                              data-testid={`delete-target-${target.id}`}
                              onClick={() => setDeletingTarget(target)}
                              className="px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-rose-950/40 hover:border-rose-700/60 hover:text-rose-400 transition-all flex items-center gap-1.5"
                              title="Delete Target"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                              Delete
                            </button>
                          </div>
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
      />

      <DeleteTargetModal
        isOpen={!!deletingTarget}
        target={deletingTarget}
        onClose={() => setDeletingTarget(null)}
        onConfirm={handleConfirmDelete}
        isDeleting={deleteTargetMutation.isPending}
      />
    </div>
  );
}
