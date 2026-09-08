import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useCheckQuery, useTargetQuery, useConfigQuery } from '../hooks/useTargetDetail';
import { getSnapshotText } from '../api/snapshots';
import { TargetStatusBadge } from '../components/TargetStatusBadge';
import { ScreenshotCompare } from '../components/ScreenshotCompare';
import { TextDiffView } from '../components/TextDiffView';
import { ArtifactError } from '../components/ArtifactError';
import { TargetStatus } from '../types/target';
import { formatDateTime } from '../utils/date';

export function CheckDetailPage() {
  const { id } = useParams<{ id: string }>();
  const checkId = id || '';

  const { data: check, isLoading: isCheckLoading, isError: isCheckError } = useCheckQuery(checkId);
  const targetId = check?.target_id || '';
  const { data: target, isLoading: isTargetLoading } = useTargetQuery(targetId);
  const { data: appConfig } = useConfigQuery();

  const baselineSnapshotId = check?.baseline_snapshot_id;
  const currentSnapshotId = check?.current_snapshot_id;

  // A check can reference the same snapshot on both sides; then one fetch covers both.
  const isSameSnapshot = !!currentSnapshotId && currentSnapshotId === baselineSnapshotId;

  // Text retrieval queries. Note there is deliberately no `= ''` default: an
  // undefined artifact must stay distinguishable from one that loaded empty.
  const baselineTextQuery = useQuery({
    queryKey: ['snapshotText', baselineSnapshotId],
    queryFn: () => getSnapshotText(baselineSnapshotId!),
    enabled: !!baselineSnapshotId,
  });

  const currentTextQuery = useQuery({
    queryKey: ['snapshotText', currentSnapshotId],
    queryFn: () => getSnapshotText(currentSnapshotId!),
    enabled: !!currentSnapshotId && !isSameSnapshot,
  });

  const isTextLoading =
    baselineTextQuery.isLoading || (!isSameSnapshot && currentTextQuery.isLoading);

  const failedTextArtifacts = [
    baselineTextQuery.isError ? 'baseline text' : null,
    !isSameSnapshot && currentTextQuery.isError ? 'current text' : null,
  ].filter((name): name is string => name !== null);

  const baselineText = baselineTextQuery.data;
  const currentText = isSameSnapshot ? baselineTextQuery.data : currentTextQuery.data;
  const canRenderTextDiff = baselineText !== undefined && currentText !== undefined;

  const retryText = () => {
    if (baselineTextQuery.isError) void baselineTextQuery.refetch();
    if (!isSameSnapshot && currentTextQuery.isError) void currentTextQuery.refetch();
  };

  if (isCheckLoading || isTargetLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <svg className="animate-spin h-8 w-8 text-cyan-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <p className="text-slate-500 text-sm">Loading check details...</p>
      </div>
    );
  }

  if (isCheckError || !check) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="bg-rose-950/20 border border-rose-800/40 rounded-2xl p-8 max-w-lg mx-auto">
          <h2 className="text-xl font-semibold text-rose-400 mb-2">Check Result Not Found</h2>
          <p className="text-slate-400 text-sm mb-6">
            The historical check result you are looking for does not exist or may have been deleted.
          </p>
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm font-semibold text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            &larr; Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const textThreshold = appConfig ? `${(appConfig.text_change_threshold * 100).toFixed(1)}%` : '2.0%';
  const visualThreshold = appConfig ? `${(appConfig.visual_change_threshold * 100).toFixed(1)}%` : '1.0%';
  const structureThreshold = appConfig
    ? `${(appConfig.structure_change_threshold * 100).toFixed(1)}%`
    : '0.0%';

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Back Link to Target Detail / Breadcrumb */}
      <div className="mb-6">
        <Link
          to={target ? `/targets/${target.id}` : '/'}
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-400 hover:text-cyan-400 transition-colors group"
        >
          <span className="transform group-hover:-translate-x-1 transition-transform">&larr;</span>{' '}
          Back to {target ? target.name : 'Target'}
        </Link>
      </div>

      <header className="mb-10">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-3xl font-extrabold text-slate-100">Check Details</h1>
              <TargetStatusBadge status={check.status as TargetStatus} />
            </div>
            {target && (
              <p className="text-sm text-slate-400">
                Target:{' '}
                <Link to={`/targets/${target.id}`} className="text-cyan-400 hover:underline">
                  {target.name}
                </Link>
              </p>
            )}
          </div>
          <div className="text-left md:text-right">
            <span className="text-slate-500 block text-xs uppercase tracking-wider font-semibold">Check Executed</span>
            <span className="text-slate-300 font-mono text-sm">{formatDateTime(check.created_at)}</span>
          </div>
        </div>
      </header>

      {/* Target Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {/* Scores & Thresholds */}
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-xl shadow-lg min-w-0">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4">Comparison Scores</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-slate-500 block text-xs">Text Score</span>
              <span className="text-slate-300 font-mono font-semibold">
                {(check.text_change_score * 100).toFixed(1)}%
              </span>
              <span className="text-[10px] text-slate-500 block">Threshold: {textThreshold}</span>
            </div>
            <div>
              <span className="text-slate-500 block text-xs">Visual Score</span>
              <span className="text-slate-300 font-mono font-semibold">
                {(check.visual_change_score * 100).toFixed(1)}%
              </span>
              <span className="text-[10px] text-slate-500 block">Threshold: {visualThreshold}</span>
            </div>
            <div className="col-span-2 pt-3 border-t border-slate-800/80">
              <span className="text-slate-500 block text-xs">
                Structural Score
                <span className="text-slate-600"> — scripts, iframes, forms, outbound hosts</span>
              </span>
              <span
                className={`font-mono font-semibold ${
                  check.structure_change_score > 0 ? 'text-amber-400' : 'text-slate-300'
                }`}
              >
                {(check.structure_change_score * 100).toFixed(1)}%
              </span>
              <span className="text-[10px] text-slate-500 block">
                Threshold: {structureThreshold} — any change is reported
              </span>
            </div>
          </div>
        </div>

        {/* Check Result Details */}
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-xl shadow-lg min-w-0">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4">Summary</h3>
          <div className="min-w-0">
            <span className="text-slate-500 block text-xs mb-1">Result Summary</span>
            <p className="text-slate-300 text-sm leading-relaxed break-words [overflow-wrap:anywhere]">
              {check.summary || 'No changes detected.'}
            </p>
          </div>
        </div>

        {/* Captured Metadata Card */}
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-xl shadow-lg md:col-span-2 lg:col-span-1 min-w-0">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4">Check Metadata</h3>
          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between border-b border-slate-800/40 pb-1.5">
              <span className="text-slate-500">Check ID</span>
              <span className="text-slate-400 truncate max-w-[160px]" title={check.id}>{check.id}</span>
            </div>
            <div className="flex justify-between border-b border-slate-800/40 pb-1.5">
              <span className="text-slate-500">Baseline ID</span>
              <span className="text-slate-400 truncate max-w-[160px]" title={check.baseline_snapshot_id}>
                {check.baseline_snapshot_id}
              </span>
            </div>
            <div className="flex justify-between border-b border-slate-800/40 pb-1.5">
              <span className="text-slate-500">Current ID</span>
              <span className="text-slate-400 truncate max-w-[160px]" title={check.current_snapshot_id}>
                {check.current_snapshot_id}
              </span>
            </div>
            <div className="flex justify-between pb-1">
              <span className="text-slate-500">Acknowledged</span>
              <span className="text-slate-400">
                {check.acknowledged_at ? formatDateTime(check.acknowledged_at) : 'No'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Screenshot Compare Component */}
      <div className="mb-8">
        <ScreenshotCompare
          baselineSnapshotId={baselineSnapshotId}
          currentSnapshotId={currentSnapshotId}
        />
      </div>

      {/* Text Diff Component */}
      <div>
        {isTextLoading ? (
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-12 text-center text-slate-500 flex items-center justify-center gap-3">
            <svg className="animate-spin h-5 w-5 text-cyan-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span className="text-sm">Calculating diffs...</span>
          </div>
        ) : failedTextArtifacts.length > 0 ? (
          <ArtifactError
            title="Text comparison unavailable"
            failedArtifacts={failedTextArtifacts}
            onRetry={retryText}
            isRetrying={baselineTextQuery.isFetching || currentTextQuery.isFetching}
          />
        ) : canRenderTextDiff ? (
          <TextDiffView baselineText={baselineText} currentText={currentText} />
        ) : (
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-6 text-center text-slate-500 font-mono text-sm">
            Text artifacts are not available for this check.
          </div>
        )}
      </div>
    </div>
  );
}
