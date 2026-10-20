import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { Check, Circle, Clock3, Loader2, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/client';
import { CHECK_ACTIVITY_QUERY_KEY, useActivityTargetQuery, useCheckActivityQuery } from '../hooks/useTargets';
import { formatDateTime, parseDate } from '../utils/date';
import type { ActiveCheck, CheckProgress } from '../types/target';

const phases = ['queued', 'opening_page', 'waiting_page_ready', 'capturing', 'comparing', 'saving_result'];
const labels: Record<string, string> = {
  queued: 'Waiting for a check slot',
  opening_page: 'Open website',
  waiting_page_ready: 'Wait for page readiness',
  capturing: 'Capture page data',
  comparing: 'Compare with baselines',
  saving_result: 'Save result',
};

interface Props {
  wide: boolean;
}

export function ActiveChecksPanel({ wide }: Props) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const focusDetailsRef = useRef(false);
  const detailsHeadingRef = useRef<HTMLHeadingElement>(null);
  const activityQuery = useCheckActivityQuery(wide, 20, offset);
  const activity = activityQuery.data;
  const items = useMemo(() => activity?.items ?? [], [activity?.items]);
  const selected = items.find((item) => item.id === selectedId) ?? null;
  const selectedTargetQuery = useActivityTargetQuery(
    selectedId ?? '',
    wide && Boolean(selectedId) && !selected,
  );
  const selectedTarget = selectedTargetQuery.isError ? null : selectedTargetQuery.data;
  const progress: CheckProgress | null = selected?.progress ?? selectedTarget?.check_progress ?? null;
  const selectedName = selected?.name ?? selectedTarget?.name;
  const total = activity?.total ?? 0;
  const terminal = progress?.state === 'finished';
  const attemptStartedAt = progress?.attempt_started_at;

  useEffect(() => {
    if (selectedId === null && items.length) setSelectedId(items[0].id);
  }, [items, selectedId]);

  useEffect(() => {
    if (activity && total > 0 && offset >= total) {
      setOffset(Math.max(0, Math.floor((total - 1) / 20) * 20));
    }
  }, [activity, offset, total]);

  useEffect(() => {
    if (focusDetailsRef.current && selectedName && detailsHeadingRef.current) {
      detailsHeadingRef.current.focus();
      focusDetailsRef.current = false;
    }
  }, [selectedId, selectedName]);

  useEffect(() => {
    if (!wide || !attemptStartedAt || terminal) return;
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - parseDate(attemptStartedAt).getTime()) / 1000)));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [wide, attemptStartedAt, terminal]);

  useEffect(() => {
    const onAccessDenied = (event: Event) => {
      const status = (event as CustomEvent<{ status?: number }>).detail?.status;
      if (status === 401 || status === 403 || status === 404) {
        setSelectedId(null);
        queryClient.removeQueries({ queryKey: CHECK_ACTIVITY_QUERY_KEY });
      }
    };
    window.addEventListener('api:access-denied', onAccessDenied);
    return () => window.removeEventListener('api:access-denied', onAccessDenied);
  }, [queryClient]);

  const selectedTerminal = selectedTarget && !selectedTarget.check_run_id;
  const selectedTargetError = selectedTargetQuery.error;

  return (
    <aside aria-label="Active checks" className="hidden min-[1680px]:block min-w-0">
      <section className="sticky top-20 flex max-h-[calc(100vh-6rem)] flex-col overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/50 shadow-xl">
        <header className="flex items-center justify-between border-b border-slate-800/80 px-4 py-4">
          <div>
            <h2 className="font-semibold text-slate-100">Active Checks</h2>
            <p className="mt-1 text-[11px] text-slate-500">All active monitors you can access</p>
          </div>
          {activity && <span className="rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-400">{total}</span>}
        </header>

        <div className="min-h-0 overflow-y-auto">
          {activityQuery.isPending ? (
            <p className="px-4 py-5 text-sm text-slate-400" role="status">Loading active checks…</p>
          ) : activityQuery.isError && !activity ? (
            <div className="space-y-2 px-4 py-5 text-sm text-rose-300" role="alert">
              <p>Unable to load active checks.</p>
              <button type="button" onClick={() => void activityQuery.refetch()} className="text-cyan-300 underline">Retry</button>
            </div>
          ) : activity && total === 0 ? (
            <div className="px-4 py-5 text-sm text-slate-400">
              <p>No active checks</p>
              {activityQuery.isRefetchError && <p className="mt-2 text-xs text-amber-300" role="status">Refresh failed · Last confirmed at {formatDateTime(activity.observed_at)}.</p>}
            </div>
          ) : (
            <>
              {activityQuery.isRefetchError && <p className="px-4 pt-3 text-xs text-amber-300" role="status">Refresh failed · Showing last known activity from {formatDateTime(activity?.observed_at)}.</p>}
              {activity && <ul className="divide-y divide-slate-800/70">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      aria-pressed={selectedId === item.id}
                      onClick={() => {
                        focusDetailsRef.current = true;
                        setSelectedId(item.id);
                      }}
                      className={'w-full px-4 py-3 text-left transition-colors hover:bg-slate-800/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-400 ' + (selectedId === item.id ? 'bg-slate-800/50' : '')}
                    >
                      <span className="block truncate text-sm font-medium text-slate-200">{item.name}</span>
                      <span className="mt-1 block truncate text-xs text-cyan-300">{activityLabel(item)}</span>
                      <span className="mt-1 block text-[11px] text-slate-500">
                        Attempt {Math.max(1, item.progress?.attempt_number ?? item.check_attempt_count)}/{item.check_retry_max_attempts}
                      </span>
                    </button>
                  </li>
                ))}
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

        {selectedId && <div className="border-t border-slate-800/80 p-4" aria-live="polite">
          {selectedTargetError ? (
            <p className="text-xs text-amber-300" role="status">
              {selectedTargetError instanceof ApiError && selectedTargetError.status === 404
                ? 'This monitor is no longer available to this account.'
                : 'Unable to confirm the latest check result.'}
            </p>
          ) : !selectedName ? (
            <p className="text-xs text-slate-400" role="status">Confirming the latest check result…</p>
          ) : (
            <ProgressDetail
              id={selectedId}
              name={selectedName}
              headingRef={detailsHeadingRef}
              progress={progress}
              status={selected?.status ?? selectedTarget?.status}
              nextCheckAt={selected?.next_check_at ?? selectedTarget?.next_check_at ?? null}
              elapsed={elapsed}
              resultKnown={Boolean(selectedTerminal || terminal)}
            />
          )}
        </div>}
      </section>
    </aside>
  );
}

function activityLabel(item: ActiveCheck): string {
  if (item.progress?.state === 'retry_wait' || item.next_check_at) {
    return item.next_check_at ? 'Retry scheduled · ' + formatDateTime(item.next_check_at) : 'Retry scheduled';
  }
  if (item.progress?.state === 'queued') return 'Waiting for a check slot';
  if (!item.progress) return 'Progress details unavailable';
  return labels[item.progress.phase] ?? 'Check in progress';
}

function ProgressDetail({
  id,
  name,
  headingRef,
  progress,
  status,
  nextCheckAt,
  elapsed,
  resultKnown,
}: {
  id: string;
  name: string;
  headingRef: RefObject<HTMLHeadingElement>;
  progress: CheckProgress | null;
  status?: string;
  nextCheckAt: string | null;
  elapsed: number;
  resultKnown: boolean;
}) {
  const steps = progress?.steps ?? [];
  return (
    <div>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 ref={headingRef} className="truncate text-sm font-semibold text-slate-100" tabIndex={-1}>{name}</h3>
          <p className="mt-1 text-[11px] text-slate-400">
            {progress?.state === 'finished' ? 'Check ' + (progress.outcome ?? status ?? 'finished') : labels[progress?.phase ?? 'queued'] ?? 'Progress details unavailable'}
          </p>
        </div>
        <Link to={'/targets/' + id} className="shrink-0 text-xs text-cyan-300 hover:text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400">View</Link>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">
        {progress?.state === 'finished' ? 'Finished · ' + (progress.outcome ?? status ?? 'Result recorded') : 'Elapsed ' + elapsed + 's · Attempt ' + Math.max(1, progress?.attempt_number ?? 1)}
      </p>
      {progress?.error_code === 'attempt_finalization_unconfirmed' && <p className="mt-2 text-xs text-amber-300" role="status">Check result is known, but attempt finalization could not be confirmed.</p>}
      {!progress && <p className="mt-3 text-xs text-slate-400">Progress details unavailable</p>}
      {progress && <ol className="mt-3 space-y-2">
        {phases.map((phase) => {
          const step = [...steps].reverse().find((item) => item.phase === phase);
          const state = step?.state ?? 'pending';
          const Icon = state === 'completed' ? Check : state === 'running' ? Loader2 : state === 'retry_wait' ? Clock3 : state === 'failed' ? X : Circle;
          const color = state === 'completed' ? 'text-emerald-400' : state === 'running' ? 'text-cyan-300' : state === 'failed' ? 'text-rose-400' : 'text-slate-500';
          const text = state === 'completed' ? 'Done' : state === 'running' ? 'Running' : state === 'skipped' ? 'Skipped' : state === 'retry_wait' ? 'Waiting' : state === 'failed' ? 'Failed' : 'Pending';
          return <li key={phase} className="flex items-center gap-2 text-[11px] text-slate-300">
            <Icon aria-hidden="true" size={13} className={color + (state === 'running' ? ' animate-spin motion-reduce:animate-none' : '')} />
            <span>{text} · {labels[phase] ?? phase}</span>
          </li>;
        })}
      </ol>}
      {nextCheckAt && <p className="mt-2 text-xs text-amber-300">Next attempt · {formatDateTime(nextCheckAt)}</p>}
      {resultKnown && status && <p className="sr-only">The latest recorded result is {status}.</p>}
    </div>
  );
}
