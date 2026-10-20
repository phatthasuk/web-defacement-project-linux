import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/client';
import { CHECK_ACTIVITY_QUERY_KEY, TARGETS_QUERY_KEY, useActivityTargetQuery, useCheckActivityQuery } from '../hooks/useTargets';
import { formatDateTime, parseDate } from '../utils/date';
import type { ActiveCheck, CheckProgress, Target } from '../types/target';
import { CheckProgressDetails } from './CheckProgressDetails';

const labels: Record<string, string> = {
  queued: 'Waiting for a check slot',
  opening_page: 'Open website',
  waiting_page_ready: 'Wait for page readiness',
  capturing: 'Capture page data',
  comparing: 'Compare with baselines',
  saving_result: 'Save result',
};
const TERMINAL_RETENTION_MS = 60_000;

interface Props {
  wide: boolean;
}

type ActivityCard = Omit<ActiveCheck, 'check_run_id'> & {
  check_run_id: string | null;
  retained: boolean;
};

export function ActiveChecksPanel({ wide }: Props) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState<ActiveCheck | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [terminalConfirmedAt, setTerminalConfirmedAt] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [selectionNotice, setSelectionNotice] = useState<string | null>(null);
  const revealRef = useRef(false);
  const restorePanelFocusRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const selectedCardRef = useRef<HTMLLIElement>(null);
  const panelHeadingRef = useRef<HTMLHeadingElement>(null);
  const activityQuery = useCheckActivityQuery(wide, 20, offset);
  const activity = activityQuery.data;
  const items = useMemo(() => activity?.items ?? [], [activity?.items]);
  const selected = items.find((item) => item.id === selectedId) ?? null;
  const selectedTargetQuery = useActivityTargetQuery(
    selectedId ?? '',
    wide && Boolean(selectedId) && !selected,
  );
  const selectedTarget = selectedTargetQuery.isError ? undefined : selectedTargetQuery.data ?? undefined;
  const targetProgress = matchingTargetProgress(selectedTarget, selectedSnapshot);
  const progress: CheckProgress | null = matchingActivityProgress(selected) ?? targetProgress;
  const total = activity?.total ?? 0;
  const terminal = progress?.state === 'finished';
  const attemptStartedAt = progress?.attempt_started_at;
  const selectedOutsidePage = Boolean(selectedId && !selected);
  const retainedCard = selectedOutsidePage && selectedSnapshot
    ? makeRetainedCard(selectedSnapshot, selectedTarget, selectedTargetQuery.isFetching, selectedTargetQuery.isError, targetProgress)
    : null;
  const displayedItems: ActivityCard[] = [
    ...items.map((item) => ({ ...item, retained: false })),
    ...(retainedCard ? [retainedCard] : []),
  ];

  useEffect(() => {
    if (selected) {
      if (selectedSnapshot !== selected) setSelectedSnapshot(selected);
      setTerminalConfirmedAt(null);
    }
  }, [selected, selectedSnapshot]);

  useEffect(() => {
    if (restorePanelFocusRef.current && panelHeadingRef.current) {
      panelHeadingRef.current.focus();
      restorePanelFocusRef.current = false;
    }
  }, [selectedId]);

  useEffect(() => {
    if (selectedId === null || selected || !selectedTarget || selectedTargetQuery.isFetching || selectedTargetQuery.isError) {
      return;
    }
    if (selectedTarget.check_run_id || selectedTarget.status === 'Checking') {
      setTerminalConfirmedAt(null);
      return;
    }
    setTerminalConfirmedAt((previous) => previous ?? Date.now());
  }, [selectedId, selected, selectedTarget, selectedTargetQuery.isFetching, selectedTargetQuery.isError]);

  useEffect(() => {
    if (activity && total > 0 && offset >= total) {
      setOffset(Math.max(0, Math.floor((total - 1) / 20) * 20));
    }
  }, [activity, offset, total]);

  useLayoutEffect(() => {
    if (!selectedOutsidePage || !(selectedTargetQuery.error instanceof ApiError) || selectedTargetQuery.error.status !== 404) return;
    restorePanelFocusRef.current = Boolean(selectedCardRef.current?.contains(document.activeElement));
    setSelectionNotice('The selected monitor is no longer available.');
    setAnnouncement('');
    setSelectedId(null);
    setSelectedSnapshot(null);
    setExpandedId(null);
    setTerminalConfirmedAt(null);
    queryClient.removeQueries({ queryKey: CHECK_ACTIVITY_QUERY_KEY });
    if (selectedId) queryClient.removeQueries({ queryKey: [...TARGETS_QUERY_KEY, selectedId] });
  }, [queryClient, selectedId, selectedOutsidePage, selectedTargetQuery.error]);

  useLayoutEffect(() => {
    if (!revealRef.current || !selectedCardRef.current || !scrollRef.current) return;
    revealRef.current = false;
    const card = selectedCardRef.current;
    const container = scrollRef.current;
    const summary = card.querySelector('button[data-card-summary="true"]');
    const details = card.querySelector('[data-card-details="true"]');
    if (!summary) return;

    const containerRect = container.getBoundingClientRect();
    const summaryRect = summary.getBoundingClientRect();
    let delta = 0;
    if (summaryRect.top < containerRect.top) delta = summaryRect.top - containerRect.top;
    else if (details) {
      const detailsRect = details.getBoundingClientRect();
      const desiredBottom = detailsRect.top + Math.min(48, detailsRect.height);
      if (desiredBottom > containerRect.bottom) delta = desiredBottom - containerRect.bottom;
    } else if (summaryRect.bottom > containerRect.bottom) delta = summaryRect.bottom - containerRect.bottom;
    if (delta) container.scrollTop += delta;
  }, [expandedId]);

  useEffect(() => {
    if (!expandedId || !wide || !attemptStartedAt || terminal) {
      setElapsed(0);
      return;
    }
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - parseDate(attemptStartedAt).getTime()) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [expandedId, wide, attemptStartedAt, terminal]);

  useEffect(() => {
    if (!terminalConfirmedAt || !selectedOutsidePage) return;
    const remaining = Math.max(0, terminalConfirmedAt + TERMINAL_RETENTION_MS - Date.now());
    const timer = window.setTimeout(() => {
      restorePanelFocusRef.current = Boolean(selectedCardRef.current?.contains(document.activeElement));
      setSelectedId(null);
      setSelectedSnapshot(null);
      setExpandedId(null);
      setTerminalConfirmedAt(null);
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [terminalConfirmedAt, selectedOutsidePage]);

  const announcementKey = selectedId && progress
    ? [selectedId, progress.run_id, progress.url_revision, progress.attempt_number, progress.phase, progress.state, progress.outcome].join(':')
    : selectedId && selectedTargetQuery.isError
      ? `${selectedId}:error:${selectedTargetQuery.errorUpdatedAt}`
      : '';
  useEffect(() => {
    if (!announcementKey) return;
    if (progress) {
      const name = selected?.name ?? selectedTarget?.name ?? selectedSnapshot?.name ?? 'Selected monitor';
      setAnnouncement(`${name}: ${progress.state === 'finished' ? progress.outcome ?? 'check finished' : labels[progress.phase] ?? 'Check in progress'}`);
    } else if (selectedTargetQuery.isError && !(selectedTargetQuery.error instanceof ApiError && selectedTargetQuery.error.status === 404)) {
      setAnnouncement('Unable to confirm the selected monitor status.');
    }
  }, [announcementKey, progress, selected, selectedId, selectedSnapshot, selectedTarget, selectedTargetQuery.error, selectedTargetQuery.isError]);

  useEffect(() => {
    const onAccessDenied = (event: Event) => {
      const status = (event as CustomEvent<{ status?: number }>).detail?.status;
      if (status === 401 || status === 403 || status === 404) {
        restorePanelFocusRef.current = Boolean(selectedCardRef.current?.contains(document.activeElement));
        setAnnouncement('');
        setSelectedId(null);
        setSelectedSnapshot(null);
        setExpandedId(null);
        setTerminalConfirmedAt(null);
        queryClient.removeQueries({ queryKey: CHECK_ACTIVITY_QUERY_KEY });
        if (selectedId) queryClient.removeQueries({ queryKey: [...TARGETS_QUERY_KEY, selectedId] });
      }
    };
    window.addEventListener('api:access-denied', onAccessDenied);
    return () => window.removeEventListener('api:access-denied', onAccessDenied);
  }, [queryClient, selectedId]);

  const selectedTargetError = selectedTargetQuery.error;
  const empty = activity && total === 0 && !retainedCard;

  return (
    <aside aria-label="Active checks" className="hidden min-[1680px]:block min-w-0">
      <section className="sticky top-20 flex max-h-[calc(100vh-6rem)] flex-col overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/50 shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-800/80 px-4 py-4">
          <div>
            <h2 ref={panelHeadingRef} tabIndex={-1} className="font-semibold text-slate-100">Active Checks</h2>
            <p className="mt-1 text-[11px] text-slate-500">All active monitors you can access</p>
          </div>
          {activity && <span className="rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-400">{total}</span>}
        </header>

        <div ref={scrollRef} className="min-h-0 overflow-y-auto">
          {selectionNotice && <p className="px-4 pt-3 text-xs text-amber-300" role="status">{selectionNotice}</p>}
          {activityQuery.isPending ? (
            <p className="px-4 py-5 text-sm text-slate-400" role="status">Loading active checks…</p>
          ) : activityQuery.isError && !activity ? (
            <div className="space-y-2 px-4 py-5 text-sm text-rose-300" role="alert">
              <p>Unable to load active checks.</p>
              <button type="button" onClick={() => void activityQuery.refetch()} className="text-cyan-300 underline">Retry</button>
            </div>
          ) : empty ? (
            <div className="px-4 py-5 text-sm text-slate-400">
              <p>No active checks</p>
              {activityQuery.isRefetchError && <p className="mt-2 text-xs text-amber-300" role="status">Refresh failed · Last confirmed at {formatDateTime(activity.observed_at)}.</p>}
            </div>
          ) : (
            <>
              {activityQuery.isRefetchError && <p className="px-4 pt-3 text-xs text-amber-300" role="status">Refresh failed · Showing last known activity from {formatDateTime(activity?.observed_at)}.</p>}
              {activity && <ul className="divide-y divide-slate-800/70">
                {displayedItems.map((item) => {
                  const isExpanded = expandedId === item.id;
                  const isSelected = selectedId === item.id;
                  const cardProgress = item.id === selectedId ? progress : matchingActivityProgress(item as ActiveCheck);
                  const titleId = `active-check-${item.id}-title`;
                  const detailId = `active-check-${item.id}-details`;
                  const confirmationPending = item.retained && selectedTargetQuery.isFetching;
                  const targetError = item.retained && selectedTargetQuery.isError;
                  return (
                    <li
                      key={item.id}
                      ref={isSelected ? selectedCardRef : undefined}
                      className={isExpanded ? 'bg-slate-800/50 ring-1 ring-inset ring-cyan-500/40' : ''}
                    >
                      <div className="flex items-start gap-2 px-4 py-3">
                        <button
                          type="button"
                          data-card-summary="true"
                          aria-expanded={isExpanded}
                          aria-controls={isExpanded ? detailId : undefined}
                          onClick={() => {
                            setSelectionNotice(null);
                            if (isExpanded) {
                              setExpandedId(null);
                              return;
                            }
                            setSelectedId(item.id);
                            setSelectedSnapshot(item.retained ? selectedSnapshot : item as ActiveCheck);
                            setTerminalConfirmedAt(item.retained && !item.check_run_id ? terminalConfirmedAt : null);
                            setExpandedId(item.id);
                            revealRef.current = true;
                          }}
                          className="min-w-0 flex-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400"
                        >
                          <span id={titleId} className="block truncate text-sm font-semibold text-slate-200">{item.name}</span>
                          <span className="mt-1 block truncate text-xs text-cyan-300">
                            {confirmationPending ? 'Confirming latest check status…' : targetError ? 'Latest status unavailable' : item.retained && item.check_run_id ? 'Active check outside this page' : item.retained && item.status !== 'Checking' ? 'Completed recently' : item.retained ? 'Check state unavailable' : activityLabel(item as ActiveCheck)}
                          </span>
                          <span className="mt-1 block text-[11px] text-slate-500">
                            Attempt {Math.max(1, cardProgress?.attempt_number ?? item.check_attempt_count)}/{item.check_retry_max_attempts}
                          </span>
                        </button>
                        <div className="flex shrink-0 items-center gap-2">
                          <Link to={'/targets/' + item.id} aria-label={`View ${item.name}`} className="text-xs text-cyan-300 hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400">View</Link>
                          {isExpanded ? <ChevronUp aria-hidden="true" size={15} className="text-slate-400" /> : <ChevronDown aria-hidden="true" size={15} className="text-slate-400" />}
                        </div>
                      </div>
                      {isExpanded && <div id={detailId} data-card-details="true" role="region" aria-labelledby={titleId} className="border-t border-slate-700/70 px-4 py-3">
                        {targetError ? (
                          <p className="text-xs text-amber-300" role="status">
                            {selectedTargetError instanceof ApiError && selectedTargetError.status === 404
                              ? 'This monitor is no longer available to this account.'
                              : 'Unable to confirm the latest check result.'}
                          </p>
                        ) : confirmationPending ? (
                          <p className="text-xs text-slate-400" role="status">Confirming the latest check result…</p>
                        ) : (
                          <CheckProgressDetails
                            progress={cardProgress}
                            status={item.id === selectedId ? selected?.status ?? selectedTarget?.status ?? item.status : item.status}
                            nextCheckAt={item.next_check_at}
                            elapsed={elapsed}
                            resultKnown={Boolean(item.retained && !item.check_run_id && item.status !== 'Checking' || cardProgress?.state === 'finished')}
                          />
                        )}
                      </div>}
                    </li>
                  );
                })}
              </ul>}
              {activity && total > 20 && <div className="flex items-center justify-between border-t border-slate-800 px-4 py-3 text-[11px] text-slate-400">
                <span>Showing {offset + 1}–{Math.min(offset + items.length, total)} of {total}</span>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setOffset((value) => Math.max(0, value - 20))} disabled={offset === 0} className="disabled:opacity-40">Previous</button>
                  <button type="button" onClick={() => setOffset((value) => value + 20)} disabled={offset + 20 >= total} className="disabled:opacity-40">Next</button>
                </div>
              </div>}
            </>
          )}
        </div>
        <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
      </section>
    </aside>
  );
}

function matchingActivityProgress(item: ActiveCheck | null): CheckProgress | null {
  if (!item?.progress || item.progress.run_id !== item.check_run_id || item.progress.url_revision !== item.url_revision) return null;
  return item.progress;
}

function matchingTargetProgress(target: Target | undefined, snapshot: ActiveCheck | null): CheckProgress | null {
  const progress = target?.check_progress;
  const runId = target?.check_run_id ?? snapshot?.check_run_id;
  if (!progress || !runId || progress.run_id !== runId || progress.url_revision !== target?.url_revision || (snapshot && snapshot.url_revision !== target?.url_revision)) return null;
  return progress;
}

function makeRetainedCard(
  snapshot: ActiveCheck,
  target: Target | undefined,
  isFetching: boolean,
  isError: boolean,
  progress: CheckProgress | null,
): ActivityCard {
  if (isError || !target) {
    return { ...snapshot, retained: true };
  }
  return {
    ...snapshot,
    name: target.name,
    status: target.status,
    url_revision: target.url_revision,
    check_run_id: target.check_run_id ?? null,
    check_run_source: target.check_run_source ?? snapshot.check_run_source,
    check_attempt_count: target.check_attempt_count ?? snapshot.check_attempt_count,
    check_retry_max_attempts: target.check_retry_max_attempts ?? snapshot.check_retry_max_attempts,
    next_check_at: target.next_check_at ?? null,
    last_error_code: target.last_error_code ?? null,
    progress: isFetching ? snapshot.progress : progress,
    retained: true,
  };
}

function activityLabel(item: ActiveCheck): string {
  const progress = matchingActivityProgress(item);
  if (progress?.state === 'retry_wait' || item.next_check_at) {
    return item.next_check_at ? 'Retry scheduled · ' + formatDateTime(item.next_check_at) : 'Retry scheduled';
  }
  if (progress?.state === 'queued') return 'Waiting for a check slot';
  if (!progress) return 'Progress details unavailable';
  return labels[progress.phase] ?? 'Check in progress';
}
