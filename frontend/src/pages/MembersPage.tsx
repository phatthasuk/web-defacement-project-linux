import { useEffect, useState } from 'react';
import { ApiError } from '../api/client';
import { useTagsQuery } from '../hooks/useTags';
import {
  useApproveMemberMutation,
  useAssignableWebsitesQuery,
  useAssignmentWebsitesQuery,
  useAssignMemberWebsiteMutation,
  useCreateMemberMutation,
  useMemberQuery,
  useMembersQuery,
  useMemberWebsitesQuery,
  useRejectMemberMutation,
  useResetMemberPasswordMutation,
  useUnassignMemberWebsiteMutation,
  useUpdateMemberMutation,
} from '../hooks/useMembers';
import type { Member, MemberWebsite } from '../types/member';
import { formatDateTime } from '../utils/date';

const inputClass = 'rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-200';
const buttonClass =
  'rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 hover:bg-slate-700 disabled:opacity-50';

export function MembersPage() {
  const [tab, setTab] = useState<'members' | 'assignments'>('members');

  // Members tab filters & pagination
  const [status, setStatus] = useState('');
  const [memberSearch, setMemberSearch] = useState('');
  const [memberOffset, setMemberOffset] = useState(0);

  // Selected member
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editDisplayName, setEditDisplayName] = useState('');
  const [memberIncludeInactive, setMemberIncludeInactive] = useState(false);
  const [candidateWebsiteId, setCandidateWebsiteId] = useState('');

  // Create member form
  const [memberForm, setMemberForm] = useState({ username: '', display_name: '', temporary_password: '' });
  const [formError, setFormError] = useState('');

  // Reset password modal
  const [resetTarget, setResetTarget] = useState<Member | null>(null);
  const [resetPasswordValue, setResetPasswordValue] = useState('');

  // Action / mutation error
  const [actionError, setActionError] = useState('');

  // Assignments tab filters & pagination
  const [assignmentSearch, setAssignmentSearch] = useState('');
  const [assignmentOffset, setAssignmentOffset] = useState(0);
  const [view, setView] = useState('all');
  const [operatorId, setOperatorId] = useState('');
  const [includeInactive, setIncludeInactive] = useState(false);
  const [tagId, setTagId] = useState('');

  // Queries
  const {
    data: membersData,
    isLoading: isMembersLoading,
    isError: isMembersError,
    error: membersError,
  } = useMembersQuery({
    limit: 50,
    offset: memberOffset,
    status: status || undefined,
    search: memberSearch || undefined,
  });

  const { data: selectedMember } = useMemberQuery(selectedId ?? undefined);

  const { data: memberWebsitesData } = useMemberWebsitesQuery(
    selectedId ?? undefined,
    memberIncludeInactive
  );

  const { data: assignableWebsitesData } = useAssignableWebsitesQuery(memberIncludeInactive, 200);

  const {
    data: assignmentData,
    isLoading: isAssignmentsLoading,
    isError: isAssignmentsError,
    error: assignmentsError,
  } = useAssignmentWebsitesQuery({
    view,
    search: assignmentSearch || undefined,
    limit: 50,
    offset: assignmentOffset,
    includeInactive,
    operatorId: operatorId || undefined,
    tagIds: tagId ? [tagId] : undefined,
  });

  const { data: operatorOptionsData } = useMembersQuery({ limit: 200 });
  const { data: tagOptionsData } = useTagsQuery();

  // Mutations
  const createMemberMutation = useCreateMemberMutation();
  const approveMemberMutation = useApproveMemberMutation();
  const rejectMemberMutation = useRejectMemberMutation();
  const updateMemberMutation = useUpdateMemberMutation();
  const resetPasswordMutation = useResetMemberPasswordMutation();
  const assignMutation = useAssignMemberWebsiteMutation();
  const unassignMutation = useUnassignMemberWebsiteMutation();

  const members = membersData?.items ?? [];
  const pending = membersData?.pending_count ?? 0;
  const memberTotal = membersData?.total ?? 0;

  const assignedWebsites = memberWebsitesData?.items ?? [];
  const assignableWebsites = assignableWebsitesData?.items ?? [];

  const assignmentWebsites = assignmentData?.items ?? [];
  const assignmentTotal = assignmentData?.total ?? 0;
  const counts = assignmentData?.counts ?? { all: 0, unassigned: 0, assigned: 0 };

  const operatorOptions = operatorOptionsData?.items ?? [];
  const tagOptions = tagOptionsData?.items ?? [];

  useEffect(() => {
    if (selectedMember) {
      setEditDisplayName(selectedMember.display_name);
    }
  }, [selectedMember]);

  const addMember = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    setActionError('');
    createMemberMutation.mutate(memberForm, {
      onSuccess: () => {
        setMemberForm({ username: '', display_name: '', temporary_password: '' });
        setFormError('');
      },
      onError: (err) => {
        setFormError(err instanceof ApiError ? err.detail : 'Unable to create member.');
      },
    });
  };

  const handleSaveDisplayName = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedMember) return;
    setActionError('');
    updateMemberMutation.mutate(
      { memberId: selectedMember.id, payload: { display_name: editDisplayName } },
      {
        onError: (err) => {
          setActionError(err instanceof ApiError ? err.detail : 'Unable to update display name.');
        },
      }
    );
  };

  const assign = () => {
    if (!selectedMember || !candidateWebsiteId) return;
    setActionError('');
    assignMutation.mutate(
      { memberId: selectedMember.id, targetId: candidateWebsiteId },
      {
        onSuccess: () => {
          setCandidateWebsiteId('');
        },
        onError: (err) => {
          setActionError(err instanceof ApiError ? err.detail : 'Unable to assign website.');
        },
      }
    );
  };

  const remove = (targetId: string) => {
    if (!selectedMember) return;
    setActionError('');
    unassignMutation.mutate(
      { memberId: selectedMember.id, targetId },
      {
        onError: (err) => {
          setActionError(err instanceof ApiError ? err.detail : 'Unable to remove website assignment.');
        },
      }
    );
  };

  const assignForTarget = (target: MemberWebsite, memberId: number) => {
    setActionError('');
    assignMutation.mutate(
      { memberId, targetId: target.id },
      {
        onError: (err) => {
          setActionError(err instanceof ApiError ? err.detail : 'Unable to assign operator.');
        },
      }
    );
  };

  const removeForTarget = (target: MemberWebsite, memberId: number) => {
    setActionError('');
    unassignMutation.mutate(
      { memberId, targetId: target.id },
      {
        onError: (err) => {
          setActionError(err instanceof ApiError ? err.detail : 'Unable to remove operator assignment.');
        },
      }
    );
  };

  const activeError =
    actionError ||
    (tab === 'members' && isMembersError
      ? membersError instanceof ApiError
        ? membersError.detail
        : 'Unable to load members.'
      : tab === 'assignments' && isAssignmentsError
      ? assignmentsError instanceof ApiError
        ? assignmentsError.detail
        : 'Unable to load assignments.'
      : '');

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold text-white">Member Management</h1>
        <p className="mt-1 text-slate-400">Manage Operator accounts and their website access.</p>
      </header>

      <div className="mb-5 flex gap-2">
        <button
          className={buttonClass}
          onClick={() => {
            setTab('members');
            setSelectedId(null);
            setActionError('');
          }}
        >
          Members <span className="ml-1 rounded-full bg-amber-900 px-2 text-amber-200">{pending} pending</span>
        </button>
        <button
          className={buttonClass}
          onClick={() => {
            setTab('assignments');
            setSelectedId(null);
            setActionError('');
          }}
        >
          Website Assignments
        </button>
      </div>

      {activeError && (
        <p role="alert" className="mb-4 rounded border border-rose-800 bg-rose-950/50 p-3 text-rose-300">
          {activeError}
        </p>
      )}

      {resetTarget && (
        <form
          role="dialog"
          aria-label={`Reset password for ${resetTarget.username}`}
          className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-slate-700 bg-slate-900 p-4"
          onSubmit={(e) => {
            e.preventDefault();
            const target = resetTarget;
            const password = resetPasswordValue;
            setActionError('');
            resetPasswordMutation.mutate(
              { memberId: target.id, payload: { temporary_password: password } },
              {
                onSuccess: () => {
                  setResetTarget(null);
                  setResetPasswordValue('');
                },
                onError: (err) => {
                  setActionError(err instanceof ApiError ? err.detail : 'Unable to reset password.');
                },
              }
            );
          }}
        >
          <span className="text-sm font-medium text-slate-200">
            Reset password for <strong className="text-cyan-300">{resetTarget.display_name}</strong>:
          </span>
          <input
            required
            minLength={12}
            maxLength={200}
            type="password"
            aria-label="Temporary password"
            placeholder="Temporary password (12–200 characters)"
            className={`${inputClass} min-w-[260px] flex-1`}
            value={resetPasswordValue}
            onChange={(e) => setResetPasswordValue(e.target.value)}
          />
          <button type="submit" className={buttonClass}>
            Confirm reset
          </button>
          <button
            type="button"
            className={buttonClass}
            onClick={() => {
              setResetTarget(null);
              setResetPasswordValue('');
            }}
          >
            Cancel
          </button>
        </form>
      )}

      {tab === 'members' ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
          <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <div className="flex flex-wrap gap-3">
              <input
                className={inputClass}
                placeholder="Search members"
                value={memberSearch}
                onChange={(e) => {
                  setMemberSearch(e.target.value);
                  setMemberOffset(0);
                }}
              />
              <select
                className={inputClass}
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setMemberOffset(0);
                }}
              >
                <option value="">All statuses</option>
                <option value="pending">Pending</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-slate-500">
                  <tr>
                    <th className="p-2">Member</th>
                    <th className="p-2">Status</th>
                    <th className="p-2">Last login</th>
                    <th className="p-2">Websites</th>
                    <th className="p-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => (
                    <tr key={m.id} className="border-t border-slate-800">
                      <td className="p-2">
                        <button
                          className="text-cyan-300 hover:underline"
                          onClick={() => {
                            setSelectedId(m.id);
                            setEditDisplayName(m.display_name);
                          }}
                        >
                          {m.display_name}
                        </button>
                        <div className="text-xs text-slate-500">
                          {m.username} · {m.role}
                        </div>
                        {m.status === 'pending' && (
                          <div className="text-xs text-amber-300">
                            Registered {m.registration_at ? formatDateTime(m.registration_at) : '—'}
                          </div>
                        )}
                      </td>
                      <td className="p-2 capitalize">{m.status}</td>
                      <td className="p-2 text-slate-400">
                        {m.last_login_at ? formatDateTime(m.last_login_at) : '—'}
                      </td>
                      <td className="p-2">{m.assigned_website_count}</td>
                      <td className="p-2">
                        <div className="flex flex-wrap gap-1">
                          {m.status === 'pending' ? (
                            <>
                              <button
                                className={buttonClass}
                                onClick={() => {
                                  if (window.confirm(`Approve ${m.username}?`)) {
                                    setActionError('');
                                    approveMemberMutation.mutate(m.id, {
                                      onError: (err) =>
                                        setActionError(
                                          err instanceof ApiError ? err.detail : 'Unable to approve member.'
                                        ),
                                    });
                                  }
                                }}
                              >
                                Approve
                              </button>
                              <button
                                className={buttonClass}
                                onClick={() => {
                                  if (window.confirm(`Reject ${m.username}?`)) {
                                    const rawReason = window.prompt('Optional rejection reason');
                                    if (rawReason === null) return;
                                    const reason = rawReason.trim() || undefined;
                                    setActionError('');
                                    rejectMemberMutation.mutate(
                                      { memberId: m.id, payload: reason ? { reason } : undefined },
                                      {
                                        onError: (err) =>
                                          setActionError(
                                            err instanceof ApiError
                                              ? err.detail
                                              : 'Unable to reject member.'
                                          ),
                                      }
                                    );
                                  }
                                }}
                              >
                                Reject
                              </button>
                            </>
                          ) : m.role === 'operator' && m.status !== 'rejected' ? (
                            <button
                              className={buttonClass}
                              onClick={() => {
                                if (window.confirm(`${m.is_active ? 'Suspend' : 'Re-enable'} ${m.username}?`)) {
                                  setActionError('');
                                  updateMemberMutation.mutate(
                                    { memberId: m.id, payload: { is_active: !m.is_active } },
                                    {
                                      onError: (err) =>
                                        setActionError(
                                          err instanceof ApiError
                                            ? err.detail
                                            : 'Unable to update member status.'
                                        ),
                                    }
                                  );
                                }
                              }}
                            >
                              {m.is_active ? 'Suspend' : 'Re-enable'}
                            </button>
                          ) : null}
                          {m.role === 'operator' && m.status === 'active' && (
                            <button
                              className={buttonClass}
                              onClick={() => {
                                setResetTarget(m);
                                setResetPasswordValue('');
                              }}
                            >
                              Reset password
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {isMembersLoading && members.length === 0 && (
                <p className="p-5 text-center text-slate-500">Loading members…</p>
              )}
              {!isMembersLoading && members.length === 0 && (
                <p className="p-5 text-center text-slate-500">No members match these filters.</p>
              )}
              <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                <span>{memberTotal} members</span>
                <div className="flex gap-2">
                  <button
                    className={buttonClass}
                    disabled={!memberOffset}
                    onClick={() => setMemberOffset(Math.max(0, memberOffset - 50))}
                  >
                    Previous
                  </button>
                  <button
                    className={buttonClass}
                    disabled={memberOffset + 50 >= memberTotal}
                    onClick={() => setMemberOffset(memberOffset + 50)}
                  >
                    Next
                  </button>
                </div>
              </div>
            </div>

            <form onSubmit={addMember} className="mt-6 border-t border-slate-800 pt-5">
              <h2 className="mb-3 font-semibold text-slate-200">Add Operator</h2>
              {formError && (
                <p role="alert" className="mb-3 rounded border border-rose-800 bg-rose-950/50 p-2 text-sm text-rose-300">
                  {formError}
                </p>
              )}
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  required
                  className={inputClass}
                  placeholder="Username"
                  value={memberForm.username}
                  onChange={(e) => setMemberForm({ ...memberForm, username: e.target.value })}
                />
                <input
                  required
                  className={inputClass}
                  placeholder="Display name"
                  value={memberForm.display_name}
                  onChange={(e) => setMemberForm({ ...memberForm, display_name: e.target.value })}
                />
                <input
                  required
                  minLength={12}
                  maxLength={200}
                  type="password"
                  className={`${inputClass} sm:col-span-2`}
                  placeholder="Temporary password (12–200 characters)"
                  value={memberForm.temporary_password}
                  onChange={(e) => setMemberForm({ ...memberForm, temporary_password: e.target.value })}
                />
              </div>
              <button type="submit" className={`${buttonClass} mt-3`}>
                Create Operator
              </button>
            </form>
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
            <h2 className="text-lg font-semibold text-white">
              {selectedMember ? `Member details · ${selectedMember.display_name}` : 'Member details'}
            </h2>
            {selectedMember ? (
              <>
                <p className="mt-1 text-xs text-slate-500">
                  Assignments remain in place while this account is suspended.
                </p>
                <form className="mt-4 flex gap-2" onSubmit={handleSaveDisplayName}>
                  <input
                    className={`${inputClass} min-w-0 flex-1`}
                    aria-label="Display name"
                    value={editDisplayName}
                    onChange={(e) => setEditDisplayName(e.target.value)}
                  />
                  <button type="submit" className={buttonClass}>
                    Save name
                  </button>
                </form>

                <label className="mt-4 flex items-center gap-2 text-sm text-slate-400">
                  <input
                    type="checkbox"
                    checked={memberIncludeInactive}
                    onChange={(e) => setMemberIncludeInactive(e.target.checked)}
                  />
                  Include inactive websites
                </label>

                <div className="mt-4 flex gap-2">
                  <select
                    className={`${inputClass} min-w-0 flex-1`}
                    value={candidateWebsiteId}
                    onChange={(e) => setCandidateWebsiteId(e.target.value)}
                  >
                    <option value="">Select website to assign</option>
                    {assignableWebsites
                      .filter((w) => !assignedWebsites.some((a) => a.id === w.id))
                      .map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.name}
                          {w.is_active ? '' : ' (inactive)'}
                        </option>
                      ))}
                  </select>
                  <button
                    type="button"
                    className={buttonClass}
                    disabled={!candidateWebsiteId}
                    onClick={assign}
                  >
                    Assign
                  </button>
                </div>

                <ul className="mt-4 divide-y divide-slate-800">
                  {assignedWebsites.map((w) => (
                    <li key={w.id} className="flex items-center justify-between gap-3 py-3">
                      <div>
                        <div className="text-sm text-slate-200">
                          {w.name}
                          {w.is_active ? '' : ' · inactive'}
                        </div>
                        <div className="text-xs text-slate-500">{w.url}</div>
                      </div>
                      <button type="button" className={buttonClass} onClick={() => remove(w.id)}>
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
                {assignedWebsites.length === 0 && (
                  <p className="mt-5 text-sm text-slate-500">No websites assigned.</p>
                )}
              </>
            ) : (
              <p className="mt-3 text-sm text-slate-500">Select a member to review assignments and details.</p>
            )}
          </section>
        </div>
      ) : (
        <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
          <div className="flex flex-wrap gap-3">
            <input
              className={inputClass}
              placeholder="Search websites by name or URL"
              value={assignmentSearch}
              onChange={(e) => {
                setAssignmentSearch(e.target.value);
                setAssignmentOffset(0);
              }}
            />
            <select
              className={inputClass}
              value={view}
              onChange={(e) => {
                setView(e.target.value);
                setAssignmentOffset(0);
              }}
            >
              <option value="all">All ({counts.all})</option>
              <option value="unassigned">Unassigned ({counts.unassigned})</option>
              <option value="assigned">Assigned ({counts.assigned})</option>
            </select>
            <select
              className={inputClass}
              value={operatorId}
              onChange={(e) => {
                setOperatorId(e.target.value);
                setAssignmentOffset(0);
              }}
            >
              <option value="">Any Operator</option>
              {operatorOptions
                .filter((m) => m.role === 'operator')
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name} ({m.status})
                  </option>
                ))}
            </select>
            <select
              className={inputClass}
              value={tagId}
              onChange={(e) => {
                setTagId(e.target.value);
                setAssignmentOffset(0);
              }}
            >
              <option value="">All tags</option>
              {tagOptions.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input
                type="checkbox"
                checked={includeInactive}
                onChange={(e) => {
                  setIncludeInactive(e.target.checked);
                  setAssignmentOffset(0);
                }}
              />
              Include inactive
            </label>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-slate-500">
                <tr>
                  <th className="p-2">Website</th>
                  <th className="p-2">Tags</th>
                  <th className="p-2">Current assignees</th>
                </tr>
              </thead>
              <tbody>
                {assignmentWebsites.map((w) => (
                  <tr key={w.id} className="border-t border-slate-800">
                    <td className="p-2">
                      <div>
                        {w.name}
                        {w.is_active ? '' : ' · inactive'}
                      </div>
                      <div className="text-xs text-slate-500">{w.url}</div>
                    </td>
                    <td className="p-2 text-slate-400">
                      {w.tags.map((t) => t.name).join(', ') || '—'}
                    </td>
                    <td className="p-2">
                      <div className="flex flex-wrap gap-2">
                        {(w.assignees || []).map((a) => (
                          <span key={a.id} className="rounded bg-slate-800 px-2 py-1 text-xs">
                            {a.display_name}
                            {a.is_active ? '' : ' (suspended)'}{' '}
                            <button
                              type="button"
                              aria-label={`Remove ${a.display_name}`}
                              onClick={() => removeForTarget(w, a.id)}
                              className="ml-1 text-rose-300"
                            >
                              ×
                            </button>
                          </span>
                        ))}
                        <select
                          className={`${inputClass} py-1 text-xs`}
                          defaultValue=""
                          onChange={(e) => {
                            if (e.target.value) assignForTarget(w, Number(e.target.value));
                            e.target.value = '';
                          }}
                        >
                          <option value="">Add assignee…</option>
                          {operatorOptions
                            .filter(
                              (m) =>
                                m.role === 'operator' &&
                                m.status !== 'pending' &&
                                m.status !== 'rejected' &&
                                !(w.assignees || []).some((a) => a.id === m.id)
                            )
                            .map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.display_name}
                                {m.is_active ? '' : ' (suspended)'}
                              </option>
                            ))}
                        </select>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {isAssignmentsLoading && assignmentWebsites.length === 0 && (
              <p className="p-6 text-center text-slate-500">Loading websites…</p>
            )}
            {!isAssignmentsLoading && assignmentWebsites.length === 0 && (
              <p className="p-6 text-center text-slate-500">No websites match these filters.</p>
            )}
            <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
              <span>{assignmentTotal} websites</span>
              <div className="flex gap-2">
                <button
                  className={buttonClass}
                  disabled={!assignmentOffset}
                  onClick={() => setAssignmentOffset(Math.max(0, assignmentOffset - 50))}
                >
                  Previous
                </button>
                <button
                  className={buttonClass}
                  disabled={assignmentOffset + 50 >= assignmentTotal}
                  onClick={() => setAssignmentOffset(assignmentOffset + 50)}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
