import { Check, Circle, Clock3, Loader2, X } from 'lucide-react';
import type { CheckProgress } from '../types/target';
import { formatDateTime } from '../utils/date';

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
  progress: CheckProgress | null;
  status: string;
  nextCheckAt?: string | null;
  elapsed: number;
  resultKnown?: boolean;
  loading?: boolean;
  refreshFailed?: boolean;
}

export function CheckProgressDetails({
  progress,
  status,
  nextCheckAt = null,
  elapsed,
  resultKnown = false,
  loading = false,
  refreshFailed = false,
}: Props) {
  const terminal = progress?.state === 'finished';
  const phaseAnnouncement = loading && !progress
    ? 'Loading check progress'
    : !progress
      ? 'Check progress details unavailable'
      : terminal
        ? `Check finished with status ${progress.outcome ?? status}`
        : `Check phase: ${labels[progress.phase] ?? progress.phase}`;

  return (
    <div aria-live="off">
      <span className="sr-only" role="status" aria-live="polite">{phaseAnnouncement}</span>
      <p role={loading && !progress ? 'status' : undefined} className="text-[11px] text-slate-400">
        {loading && !progress ? 'Loading check progress…' : terminal ? `Check ${progress.outcome ?? status}` : resultKnown && !progress ? `Recorded result · ${status}` : labels[progress?.phase ?? ''] ?? 'Progress details unavailable'}
      </p>
      <p className="mt-2 text-[11px] text-slate-500">
        {terminal ? `Finished · ${progress.outcome ?? status}` : resultKnown && !progress ? 'Final result confirmed' : `Elapsed ${elapsed}s · Attempt ${Math.max(1, progress?.attempt_number ?? 1)}`}
      </p>
      {refreshFailed && <p className="mt-3 text-xs text-amber-300" role="status">Unable to refresh progress · Showing the last known status</p>}
      {progress?.error_code === 'attempt_finalization_unconfirmed' && <p className="mt-2 text-xs text-amber-300" role="status">Check result is known, but attempt finalization could not be confirmed.</p>}
      {progress && <ol className="mt-3 space-y-2">
        {phases.map((phase) => {
          const step = [...progress.steps].reverse().find((item) => item.phase === phase);
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
      {resultKnown && <p className="sr-only">The latest recorded result is {status}.</p>}
    </div>
  );
}
