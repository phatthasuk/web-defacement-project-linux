import { useState, useEffect, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  useTargetQuery,
  useTargetSnapshotsQuery,
  useSnapshotQuery,
  useTargetBaselineSnapshotQuery,
  useTargetBaselinesQuery,
  useDemoteBaselineMutation,
  useTargetChecksQuery,
  useApproveBaselineMutation,
  useAcknowledgeCheckMutation,
  useConfirmDefacedMutation,
  useConfigQuery,
} from '../hooks/useTargetDetail';
import { useUpdateTargetMutation, useDeleteTargetMutation, useTriggerCheckMutation } from '../hooks/useTargets';
import { getSnapshotText } from '../api/snapshots';
import { listTargetChecks } from '../api/checks';
import { TargetStatusBadge } from '../components/TargetStatusBadge';
import { ScreenshotCompare } from '../components/ScreenshotCompare';
import { BaselineManagerModal } from '../components/BaselineManagerModal';
import { EditTargetModal } from '../components/EditTargetModal';
import { DeleteTargetModal } from '../components/DeleteTargetModal';
import { formatDateTime } from '../utils/date';
import { TextDiffView } from '../components/TextDiffView';
import { ArtifactError } from '../components/ArtifactError';
import { TargetStatus } from '../types/target';
import { TagBadge } from '../components/TagBadge';
import { useTagsQuery } from '../hooks/useTags';

export function TargetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const targetId = id || '';

  const { data: target, isLoading: isTargetLoading, isError: isTargetError } = useTargetQuery(targetId);
  const { data: snapshots, isLoading: isSnapshotsLoading } = useTargetSnapshotsQuery(targetId);
  const { data: baselineSnapshot, isLoading: isBaselineLoading } = useTargetBaselineSnapshotQuery(targetId);
  const { data: baselines = [], isLoading: isBaselinesLoading } = useTargetBaselinesQuery(targetId);
  const { data: checks, isLoading: isChecksLoading } = useTargetChecksQuery(targetId);
  const { data: appConfig } = useConfigQuery();
  const { data: tagData } = useTagsQuery();
  const { data: historicalChecks = [] } = useQuery({
    queryKey: ['historicalChecks', targetId, target?.url_revision],
    queryFn: () => listTargetChecks(targetId, true),
    enabled: Boolean(target && target.url_revision > 1),
  });

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
  const triggerCheckMutation = useTriggerCheckMutation();
  const [triageError, setTriageError] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const lastSignatureRef = useRef<{ targetId: string; signature: string | null } | null>(null);

  const latestCheckItem = checks?.[0];
  const checkSignature = latestCheckItem ? `${latestCheckItem.id}:${latestCheckItem.acknowledged_at ?? 'null'}:${latestCheckItem.status}` : 'no-check';
  const targetSignature = target ? `${target.status}:${target.updated_at}` : 'no-target';
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

  // A new URL has no comparison yet; display its captured candidate for approval.
  const latestSnapshot = snapshots?.[0] || null;
  const pendingCandidate = target && target.url_revision > 1 && !baselineSnapshot && !latestCheckItem
    ? latestSnapshot
    : null;
  const compareBaselineId = latestCheckItem?.baseline_snapshot_id || baselineSnapshot?.id;
  const compareCurrentId = latestCheckItem?.current_snapshot_id || pendingCandidate?.id || baselineSnapshot?.id;

  const cachedBaseline = [...baselines, ...(snapshots || [])].find(
    (snapshot) => snapshot.id === compareBaselineId
  );
  const cachedCurrent = snapshots?.find((snapshot) => snapshot.id === compareCurrentId);
  const baselineMetadataQuery = useSnapshotQuery(compareBaselineId, cachedBaseline);
  const currentMetadataQuery = useSnapshotQuery(compareCurrentId, cachedCurrent);
  const matchedBaseline = baselineMetadataQuery.data;
  const currentSnapshot = currentMetadataQuery.data;

  // The latest snapshot may itself be the baseline; then one fetch covers both.
  const isSameSnapshot = !!compareCurrentId && compareCurrentId === compareBaselineId;

  // Text retrieval queries. Note there is deliberately no `= ''` default: an
  // undefined artifact must stay distinguishable from one that loaded empty.
  const baselineTextQuery = useQuery({
    queryKey: ['snapshotText', compareBaselineId],
    queryFn: () => getSnapshotText(compareBaselineId!),
    enabled: !!compareBaselineId,
  });

  const latestTextQuery = useQuery({
    queryKey: ['snapshotText', compareCurrentId],
    queryFn: () => getSnapshotText(compareCurrentId!),
    enabled: !!compareCurrentId && !isSameSnapshot,
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
  const isInitialBaseline = !latestCheck;
  const latestCheckIsHistorical =
    target.status === 'Failed' || target.status === 'Availability Issue';

  const isChecking = target.status === 'Checking';

  const handleApproveBaseline = async () => {
    const snapshotToApprove = currentSnapshot?.id;
    if (!snapshotToApprove) return;
    setTriageError(null);
    try {
      await approveBaselineMutation.mutateAsync({
        targetId: target.id,
        snapshotId: snapshotToApprove,
      });
    } catch (err) {
      console.error('Failed to approve baseline:', err);
      setTriageError(err instanceof Error ? err.message : 'Failed to approve baseline');
    }
  };

  const handleAcknowledge = async () => {
    if (!latestCheck) return;
    setTriageError(null);
    try {
      await acknowledgeCheckMutation.mutateAsync({
        targetId: target.id,
        checkId: latestCheck.id,
      });
    } catch (err) {
      console.error('Failed to acknowledge check:', err);
      setTriageError(err instanceof Error ? err.message : 'Failed to acknowledge check');
    }
  };

  const handleConfirmDefaced = async () => {
    if (!latestCheck) return;
    setTriageError(null);
    try {
      await confirmDefacedMutation.mutateAsync({
        targetId: target.id,
        checkId: latestCheck.id,
      });
    } catch (err) {
      console.error('Failed to confirm defacement:', err);
      setTriageError(err instanceof Error ? err.message : 'Failed to confirm defacement');
    }
  };

  const handleTriggerCheck = async () => {
    setTriageError(null);
    try {
      await triggerCheckMutation.mutateAsync(target.id);
    } catch (err) {
      console.error('Failed to trigger check:', err);
      setTriageError(err instanceof Error ? err.message : 'Failed to trigger check');
    }
  };

  const handleSaveEdit = async (targetId: string, newName: string, newUrl: string, tagIds: string[]) => {
    await updateTargetMutation.mutateAsync({
      targetId,
      payload: { name: newName, url: newUrl, tag_ids: tagIds },
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
  const canApproveBaseline = Boolean(
    currentSnapshot && !currentSnapshot.is_baseline && !isSameSnapshot && (latestCheck || pendingCandidate)
  );
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

      {triageError && (
        <div data-testid="triage-error-banner" className="mb-6 p-4 bg-rose-950/40 border border-rose-800/60 rounded-xl text-rose-300 text-sm flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <svg className="h-5 w-5 shrink-0 text-rose-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>{triageError}</span>
          </div>
          <button
            onClick={() => setTriageError(null)}
            className="text-rose-400 hover:text-rose-200 text-xs font-semibold px-2 py-1 rounded hover:bg-rose-900/40 transition-colors"
            title="Dismiss error"
          >
            Dismiss
          </button>
        </div>
      )}

      <header className="mb-10 flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
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
          {(target.tags?.length ?? 0) > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(target.tags ?? []).map((tag) => <TagBadge key={tag.id} tag={tag} />)}
            </div>
          )}
          {target.status === 'Awaiting Baseline' && (
            <p className="mt-3 max-w-2xl rounded-lg border border-amber-800/60 bg-amber-950/40 p-3 text-sm text-amber-200">
              URL revision {target.url_revision} is awaiting baseline approval.
              {pendingCandidate ? ' Review the latest capture, then approve it to resume comparisons.' : ' Run a check to capture the new URL.'}
            </p>
          )}

          <div className="flex items-center gap-2 mt-3">
            <button
              data-testid="detail-check-target-btn"
              onClick={handleTriggerCheck}
              disabled={isChecking || triggerCheckMutation.isPending || !target.is_active}
              className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-cyan-950/40 border border-cyan-700/60 text-cyan-300 hover:bg-cyan-900/60 hover:border-cyan-500 hover:text-cyan-100 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-1.5"
              title={isChecking ? 'Check in progress' : !target.is_active ? 'Target is disabled' : 'Check Target Now'}
            >
              <svg className={`w-4 h-4 ${isChecking || triggerCheckMutation.isPending ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {isChecking || triggerCheckMutation.isPending ? 'Checking...' : 'Check Now'}
            </button>

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
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row lg:shrink-0">
          {canApproveBaseline && (
            <button
              onClick={handleApproveBaseline}
              disabled={isChecking || approveBaselineMutation.isPending}
              title={isChecking ? 'Cannot triage while check is in progress' : undefined}
              className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-lg bg-gradient-to-r from-emerald-500 to-teal-600 px-4 text-sm font-semibold text-white shadow-md shadow-emerald-950/20 transition-all hover:from-emerald-400 hover:to-teal-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {approveBaselineMutation.isPending
                ? 'Approving...'
                : 'Approve as Baseline'}
            </button>
          )}
          {canAcknowledge && (
            <button
              onClick={handleAcknowledge}
              disabled={isChecking || acknowledgeCheckMutation.isPending}
              title={isChecking ? 'Cannot triage while check is in progress' : undefined}
              className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-lg bg-gradient-to-r from-indigo-500 to-purple-600 px-4 text-sm font-semibold text-white shadow-md shadow-indigo-950/20 transition-all hover:from-indigo-400 hover:to-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {acknowledgeCheckMutation.isPending ? 'Acknowledging...' : 'Acknowledge Change'}
            </button>
          )}
          {canConfirmDefacement && (
            <button
              onClick={handleConfirmDefaced}
              disabled={isChecking || confirmDefacedMutation.isPending}
              title={isChecking ? 'Cannot triage while check is in progress' : undefined}
              className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-lg bg-gradient-to-r from-rose-600 to-red-700 px-4 text-sm font-semibold text-white shadow-md shadow-rose-950/30 transition-all hover:from-rose-500 hover:to-red-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {confirmDefacedMutation.isPending ? 'Confirming...' : 'Confirm Defacement'}
            </button>
          )}
        </div>
      </header>

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
            {baselineMetadataQuery.isError ? (
              <p className="text-rose-400 text-sm">Baseline metadata unavailable. Retry the page.</p>
            ) : baselineMetadataQuery.isLoading ? (
              <p className="text-slate-500 text-sm">Loading baseline metadata...</p>
            ) : matchedBaseline ? (
              <div className="space-y-3 text-sm">
                <div>
                  <span className="text-slate-500 block text-xs">
                    {latestCheck ? 'Compared Baseline ID' : 'Primary Baseline ID'}
                  </span>
                  <span className="font-mono text-slate-300 text-xs break-all">{matchedBaseline.id}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-xs">Captured At</span>
                  <span className="text-slate-300">{formatDateTime(matchedBaseline.captured_at)}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-xs">Page Title</span>
                  <span className="text-slate-300 italic break-words">{matchedBaseline.title || 'No Title'}</span>
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
          {latestCheck && isSameSnapshot ? (
            <div className="space-y-3 text-sm">
              <div className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-950/80 border border-emerald-800/60 text-emerald-400">
                Matched Baseline (Clean)
              </div>
              <div>
                <span className="text-slate-500 block text-xs">Referenced Baseline ID</span>
                <span className="font-mono text-slate-300 text-xs break-all">{compareBaselineId}</span>
              </div>
              <p className="text-xs text-slate-400">
                Latest check detected no changes. Live capture matched baseline and was discarded.
              </p>
            </div>
          ) : currentMetadataQuery.isError ? (
            <p className="text-rose-400 text-sm">Snapshot metadata unavailable. Retry the page.</p>
          ) : currentMetadataQuery.isLoading ? (
            <p className="text-slate-500 text-sm">Loading snapshot metadata...</p>
          ) : currentSnapshot ? (
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-slate-500 block text-xs">Snapshot ID</span>
                <span className="font-mono text-slate-300 text-xs break-all">{currentSnapshot.id}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-xs">Captured At</span>
                <span className="text-slate-300">{formatDateTime(currentSnapshot.captured_at)}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-xs">Page Title</span>
                <span className="text-slate-300 italic break-words">{currentSnapshot.title || 'No Title'}</span>
              </div>
            </div>
          ) : latestSnapshot ? (
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
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-4">
              {latestCheckIsHistorical ? 'Last Successful Comparison' : 'Latest Check Results'}
            </h3>
            {latestCheck ? (
              <div className="space-y-3 text-sm">
                {latestCheckIsHistorical && (
                  <p className="text-xs text-amber-400">
                    The current check failed. These results are from {formatDateTime(latestCheck.created_at)}.
                  </p>
                )}
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
            ) : pendingCandidate ? (
              <div className="text-slate-400 text-sm leading-relaxed">
                <p className="font-semibold text-amber-300 mb-1">Baseline Review Required</p>
                <p className="text-xs text-slate-500">The new URL has been captured. Approve the snapshot above before comparisons resume.</p>
              </div>
            ) : isInitialBaseline ? (
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
          baselineSnapshotId={compareBaselineId}
          currentSnapshotId={compareCurrentId}
        />
      </div>

      {/* Text Diff Component */}
      <div>
        {isInitialBaseline ? (
          <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-6 text-center text-slate-500 font-mono text-sm">
            {pendingCandidate ? 'New URL candidate awaiting approval. No differences to calculate.' : 'This is the initial snapshot. No differences to calculate.'}
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

      {target.url_revision > 1 && historicalChecks.length > 0 && (
        <section className="mt-8 rounded-xl border border-slate-800 bg-slate-900/40 p-5">
          <h2 className="mb-3 text-sm font-semibold text-slate-300">Check history across URL revisions</h2>
          <div className="space-y-2">
            {historicalChecks.filter((check) => !checks?.some((current) => current.id === check.id)).map((check) => (
              <Link key={check.id} to={`/checks/${check.id}`} className="block text-xs text-cyan-400 hover:text-cyan-300">
                {formatDateTime(check.created_at)} · {check.status} · {check.id}
              </Link>
            ))}
          </div>
        </section>
      )}

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
        availableTags={tagData?.items ?? []}
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
