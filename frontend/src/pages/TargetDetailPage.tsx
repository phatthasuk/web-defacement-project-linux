import { useState, useEffect, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  useTargetQuery,
  useTargetSnapshotsQuery,
  useTargetBaselineSnapshotQuery,
  useTargetBaselinesQuery,
  useDemoteBaselineMutation,
  useTargetChecksQuery,
  useApproveBaselineMutation,
  useAcknowledgeCheckMutation,
  useConfirmDefacedMutation,
  useConfigQuery,
} from '../hooks/useTargetDetail';
import { useUpdateTargetMutation, useDeleteTargetMutation } from '../hooks/useTargets';
import { getSnapshotText } from '../api/snapshots';
import { TargetStatusBadge } from '../components/TargetStatusBadge';
import { ScreenshotCompare } from '../components/ScreenshotCompare';
import { BaselineManagerModal } from '../components/BaselineManagerModal';
import { EditTargetModal } from '../components/EditTargetModal';
import { DeleteTargetModal } from '../components/DeleteTargetModal';
import { formatDateTime } from '../utils/date';
import { TextDiffView } from '../components/TextDiffView';
import { ArtifactError } from '../components/ArtifactError';
import { TargetStatus } from '../types/target';

export function TargetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const targetId = id || '';

  const { data: target, isLoading: isTargetLoading, isError: isTargetError } = useTargetQuery(targetId);
  const { data: snapshots, isLoading: isSnapshotsLoading } = useTargetSnapshotsQuery(targetId);
  const { data: baselineSnapshot, isLoading: isBaselineLoading } = useTargetBaselineSnapshotQuery(targetId);
  const { data: baselines = [], isLoading: isBaselinesLoading } = useTargetBaselinesQuery(targetId);
  const { data: checks, isLoading: isChecksLoading } = useTargetChecksQuery(targetId);
  const { data: appConfig } = useConfigQuery();

  const approveBaselineMutation = useApproveBaselineMutation();
  const acknowledgeCheckMutation = useAcknowledgeCheckMutation();
  const confirmDefacedMutation = useConfirmDefacedMutation();
  const demoteBaselineMutation = useDemoteBaselineMutation();

  const [isBaselineModalOpen, setIsBaselineModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const navigate = useNavigate();

  const updateTargetMutation = useUpdateTargetMutation();
  const deleteTargetMutation = useDeleteTargetMutation();

  const queryClient = useQueryClient();
  const lastSignatureRef = useRef<{ targetId: string; signature: string | null } | null>(null);

  const latestCheckItem = checks?.[0];
  const targetSignature = target ? `${target.status}:${target.updated_at}:${target.last_error ?? 'none'}` : '';
  const checkSignature = latestCheckItem ? `${latestCheckItem.id}:${latestCheckItem.acknowledged_at ?? 'null'}:${latestCheckItem.status}` : 'no-check';
  const currentSignature = target ? `${targetSignature}|${checkSignature}` : null;

  useEffect(() => {
    const previous = lastSignatureRef.current;
    // Record the target and signature together so a separate reset cannot erase
    // the initial cached value or compare results belonging to different targets.
    lastSignatureRef.current = { targetId, signature: currentSignature };
    if (
      currentSignature === null ||
      !previous ||
      previous.targetId !== targetId ||
      previous.signature === null ||
      previous.signature === currentSignature
    ) return;

    queryClient.invalidateQueries({ queryKey: ['snapshots', targetId] });
    queryClient.invalidateQueries({ queryKey: ['baseline', targetId] });
    queryClient.invalidateQueries({ queryKey: ['baselines', targetId] });
    queryClient.invalidateQueries({ queryKey: ['checks', targetId] });
  }, [currentSignature, targetId, queryClient]);

  // Find baseline and latest snapshot
  const latestSnapshot = snapshots?.[0] || null;

  // The latest snapshot may itself be the baseline; then one fetch covers both.
  const isSameSnapshot = !!latestSnapshot?.id && latestSnapshot.id === baselineSnapshot?.id;

  // Text retrieval queries. Note there is deliberately no `= ''` default: an
  // undefined artifact must stay distinguishable from one that loaded empty.
  const baselineTextQuery = useQuery({
    queryKey: ['snapshotText', baselineSnapshot?.id],
    queryFn: () => getSnapshotText(baselineSnapshot!.id),
    enabled: !!baselineSnapshot?.id,
  });

  const latestTextQuery = useQuery({
    queryKey: ['snapshotText', latestSnapshot?.id],
    queryFn: () => getSnapshotText(latestSnapshot!.id),
    enabled: !!latestSnapshot?.id && !isSameSnapshot,
  });

  const isTextLoading =
    baselineTextQuery.isLoading || (!isSameSnapshot && latestTextQuery.isLoading);

  const failedTextArtifacts = [
    baselineTextQuery.isError ? 'baseline text' : null,
    !isSameSnapshot && latestTextQuery.isError ? 'latest text' : null,
  ].filter((name): name is string => name !== null);

  const baselineText = baselineTextQuery.data;
  const latestText = isSameSnapshot ? baselineTextQuery.data : latestTextQuery.data;
  const canRenderTextDiff = baselineText !== undefined && latestText !== undefined;

  const retryText = () => {
    if (baselineTextQuery.isError) void baselineTextQuery.refetch();
    if (!isSameSnapshot && latestTextQuery.isError) void latestTextQuery.refetch();
  };

  if (isTargetLoading || isSnapshotsLoading || isBaselineLoading || isChecksLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-4">
        <svg className="animate-spin h-8 w-8 text-cyan-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        <p className="text-slate-500 text-sm">Loading target details...</p>
      </div>
    );
  }

  if (isTargetError || !target) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center">
        <div className="bg-rose-950/20 border border-rose-800/40 rounded-2xl p-8 max-w-lg mx-auto">
          <h2 className="text-xl font-semibold text-rose-400 mb-2">Target Not Found</h2>
          <p className="text-slate-400 text-sm mb-6">
            The target monitor you are looking for does not exist or may have been deleted.
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

  const latestCheck = checks?.[0] || null;
  const isOnceChecked = snapshots && snapshots.length === 1;

  const handleApproveBaseline = async () => {
    if (!latestSnapshot) return;
    try {
      await approveBaselineMutation.mutateAsync({
        targetId: target.id,
        snapshotId: latestSnapshot.id,
      });
    } catch (err) {
      console.error('Failed to approve baseline:', err);
    }
  };

  const handleAcknowledge = async () => {
    if (!latestCheck) return;
    try {
      await acknowledgeCheckMutation.mutateAsync({
        targetId: target.id,
        checkId: latestCheck.id,
      });
    } catch (err) {
      console.error('Failed to acknowledge check:', err);
    }
  };

  const handleConfirmDefaced = async () => {
    if (!latestCheck) return;
    try {
      await confirmDefacedMutation.mutateAsync({
        targetId: target.id,
        checkId: latestCheck.id,
      });
    } catch (err) {
      console.error('Failed to confirm defacement:', err);
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
    navigate('/');
  };

  const textThreshold = appConfig ? `${(appConfig.text_change_threshold * 100).toFixed(1)}%` : '2.0%';
  const visualThreshold = appConfig ? `${(appConfig.visual_change_threshold * 100).toFixed(1)}%` : '1.0%';
  const structureThreshold = appConfig
    ? `${(appConfig.structure_change_threshold * 100).toFixed(1)}%`
    : '0.0%';

  // Determine which actions are available
  const canApproveBaseline = latestSnapshot && !latestSnapshot.is_baseline;
  const canAcknowledge = latestCheck && latestCheck.status === 'Changed' && !latestCheck.acknowledged_at;
  const canConfirmDefacement = latestCheck && latestCheck.status === 'Changed' && target.status !== 'Defaced';

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Back Link & Header */}
      <div className="mb-6">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm font-semibold text-slate-400 hover:text-cyan-400 transition-colors group"
        >
          <span className="transform group-hover:-translate-x-1 transition-transform">&larr;</span> Back to Dashboard
        </Link>
      </div>

      <header className="mb-10 flex flex-col md:flex-row md:items-start md:justify-between gap-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-3xl font-extrabold text-slate-100">{target.name}</h1>
            <TargetStatusBadge
              status={target.status as TargetStatus}
              title={target.status === 'Failed' ? target.last_error || undefined : undefined}
            />
          </div>
          <div>
            <a
              href={target.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-slate-500 hover:text-cyan-400 font-mono transition-colors break-all"
            >
              {target.url}
            </a>
          </div>

          <div className="flex items-center gap-2 mt-3">
            <button
              data-testid="detail-edit-target-btn"
              onClick={() => setIsEditModalOpen(true)}
              className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-slate-800 hover:border-cyan-500/50 hover:text-cyan-300 transition-all flex items-center gap-1.5"
              title="Edit Target"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
              </svg>
              Edit
            </button>

            <button
              data-testid="detail-delete-target-btn"
              onClick={() => setIsDeleteModalOpen(true)}
              className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-slate-900 border border-slate-700/60 text-slate-300 hover:bg-rose-950/40 hover:border-rose-700/60 hover:text-rose-400 transition-all flex items-center gap-1.5"
              title="Delete Target"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
              Delete
            </button>
          </div>

          {target.status === 'Failed' && target.last_error && (
            <div className="mt-3 p-4 bg-rose-950/40 border border-rose-800/40 rounded-xl text-rose-300 text-sm max-w-2xl flex gap-3">
              <svg className="h-5 w-5 shrink-0 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <span className="font-semibold block mb-0.5">Check Execution Failed</span>
                <span className="font-mono text-xs">{target.last_error}</span>
              </div>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          {canApproveBaseline && (
            <button
              onClick={handleApproveBaseline}
              disabled={approveBaselineMutation.isPending}
              className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold text-sm rounded-lg px-4 py-2.5 transition-all shadow-md shadow-emerald-950/20 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {approveBaselineMutation.isPending ? 'Approving...' : 'Approve as Baseline'}
            </button>
          )}
          {canAcknowledge && (
            <button
              onClick={handleAcknowledge}
              disabled={acknowledgeCheckMutation.isPending}
              className="bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 text-white font-semibold text-sm rounded-lg px-4 py-2.5 transition-all shadow-md shadow-indigo-950/20 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {acknowledgeCheckMutation.isPending ? 'Acknowledging...' : 'Acknowledge Change'}
            </button>
          )}
          {canConfirmDefacement && (
            <button
              onClick={handleConfirmDefaced}
              disabled={confirmDefacedMutation.isPending}
              className="bg-gradient-to-r from-rose-600 to-red-700 hover:from-rose-500 hover:to-red-600 text-white font-semibold text-sm rounded-lg px-4 py-2.5 transition-all shadow-md shadow-rose-950/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {confirmDefacedMutation.isPending ? 'Confirming...' : 'Confirm Defacement'}
            </button>
          )}
        </div>
      </header>

      {/* Target Status Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Baseline Snapshot Card */}
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-xl shadow-lg flex flex-col justify-between min-w-0">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">Baseline Info</h3>
              <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-800/60 text-cyan-400 font-mono">
                {baselines.length} / 20 Active
              </span>
            </div>
            {baselineSnapshot ? (
              <div className="space-y-3 text-sm">
                <div>
                  <span className="text-slate-500 block text-xs">Primary Baseline ID</span>
                  <span className="font-mono text-slate-300 text-xs break-all">{baselineSnapshot.id}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-xs">Captured At</span>
                  <span className="text-slate-300">{formatDateTime(baselineSnapshot.captured_at)}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-xs">Page Title</span>
                  <span className="text-slate-300 italic break-words">{baselineSnapshot.title || 'No Title'}</span>
                </div>
              </div>
            ) : (
              <p className="text-slate-500 text-sm italic">No baseline set yet.</p>
            )}
          </div>

          <div className="pt-4 mt-4 border-t border-slate-800/60">
            <button
              type="button"
              onClick={() => setIsBaselineModalOpen(true)}
              className="w-full text-xs py-2 px-3 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 text-cyan-300 hover:text-cyan-200 border border-slate-700/60 font-medium transition-colors flex items-center justify-center gap-2 shadow-sm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <span>Manage Baselines ({baselines.length})</span>
            </button>
          </div>
        </div>

        {/* Latest Snapshot Card */}
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-xl shadow-lg min-w-0">
          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4">Latest Info</h3>
          {latestSnapshot ? (
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-slate-500 block text-xs">Snapshot ID</span>
                <span className="font-mono text-slate-300 text-xs break-all">{latestSnapshot.id}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-xs">Captured At</span>
                <span className="text-slate-300">{formatDateTime(latestSnapshot.captured_at)}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-xs">Page Title</span>
                <span className="text-slate-300 italic break-words">{latestSnapshot.title || 'No Title'}</span>
              </div>
            </div>
          ) : (
            <p className="text-slate-500 text-sm italic">No snapshots captured yet.</p>
          )}
        </div>

        {/* Latest Check Card */}
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-xl shadow-lg flex flex-col justify-between min-w-0">
          <div>
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4">Latest Check Results</h3>
            {latestCheck ? (
              <div className="space-y-3 text-sm">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-slate-500 block text-xs">Text Score</span>
                    <span className="text-slate-300 font-mono font-semibold">
                      {(latestCheck.text_change_score * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-500 block">Threshold: {textThreshold}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-xs">Visual Score</span>
                    <span className="text-slate-300 font-mono font-semibold">
                      {(latestCheck.visual_change_score * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-500 block">Threshold: {visualThreshold}</span>
                  </div>
                  <div className="col-span-2 pt-3 border-t border-slate-800/80">
                    <span className="text-slate-500 block text-xs">Structural Score</span>
                    <span
                      className={`font-mono font-semibold ${
                        latestCheck.structure_change_score > 0 ? 'text-amber-400' : 'text-slate-300'
                      }`}
                    >
                      {(latestCheck.structure_change_score * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-slate-500 block">
                      Threshold: {structureThreshold} — any change is reported
                    </span>
                  </div>
                </div>
                <div className="min-w-0">
                  <span className="text-slate-500 block text-xs mb-1">Result Summary</span>
                  <p className="text-slate-300 leading-relaxed break-words [overflow-wrap:anywhere]">
                    {latestCheck.summary || 'No changes detected.'}
                  </p>
                </div>
              </div>
            ) : isOnceChecked ? (
              <div className="text-slate-400 text-sm leading-relaxed">
                <p className="font-semibold text-slate-300 mb-1">Initial Baseline Capture</p>
                <p className="text-xs text-slate-500">
                  This is the first check for this target. Run another check to begin visual and textual comparisons.
                </p>
              </div>
            ) : (
              <p className="text-slate-500 text-sm italic">No checks executed yet.</p>
            )}
          </div>

          {latestCheck && (
            <div className="pt-3 mt-4 border-t border-slate-800/80">
              <Link
                to={`/checks/${latestCheck.id}`}
                className="text-xs font-semibold text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors"
              >
                View Full Details &rarr;
              </Link>
            </div>
          )}
        </div>
      </div>

      {/* Screenshot Compare Component */}
      <div className="mb-8">
        <ScreenshotCompare
          baselineSnapshotId={baselineSnapshot?.id}
          currentSnapshotId={latestSnapshot?.id}
        />
      </div>

      {/* Text Diff Component */}
      <div>
        {isOnceChecked ? (
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-6 text-center text-slate-500 font-mono text-sm">
            This is the initial snapshot. No differences to calculate.
          </div>
        ) : isTextLoading ? (
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
            isRetrying={baselineTextQuery.isFetching || latestTextQuery.isFetching}
          />
        ) : canRenderTextDiff ? (
          <TextDiffView baselineText={baselineText} currentText={latestText} />
        ) : (
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-6 text-center text-slate-500 font-mono text-sm">
            Text artifacts are not available for this comparison.
          </div>
        )}
      </div>

      <BaselineManagerModal
        isOpen={isBaselineModalOpen}
        onClose={() => setIsBaselineModalOpen(false)}
        targetId={targetId}
        targetName={target?.name || 'Target'}
        latestMatchedSnapshotId={latestCheck?.baseline_snapshot_id}
        baselines={baselines}
        isLoading={isBaselinesLoading}
        maxBaselines={appConfig?.max_baselines_per_target}
        onDemote={async (snapshotId) => {
          await demoteBaselineMutation.mutateAsync({ targetId, snapshotId });
        }}
        isDemoting={demoteBaselineMutation.isPending}
      />

      <EditTargetModal
        isOpen={isEditModalOpen}
        target={target}
        onClose={() => setIsEditModalOpen(false)}
        onSave={handleSaveEdit}
        isSaving={updateTargetMutation.isPending}
      />

      <DeleteTargetModal
        isOpen={isDeleteModalOpen}
        target={target}
        onClose={() => setIsDeleteModalOpen(false)}
        onConfirm={handleConfirmDelete}
        isDeleting={deleteTargetMutation.isPending}
      />
    </div>
  );
}
