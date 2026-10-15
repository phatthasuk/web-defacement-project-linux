import { useState } from 'react';
import {
  useAcknowledgeCheckMutation,
  useApproveBaselineMutation,
  useConfirmDefacedMutation,
} from './useTargetDetail';
import type { CheckResult } from '../types/checkResult';
import type { Snapshot } from '../types/snapshot';

interface UseTargetTriageActionsOptions {
  targetId: string;
  targetStatus: string;
  latestCheck: CheckResult | null;
  currentSnapshot: Snapshot | null;
  hasReviewCandidate: boolean;
  isChecking: boolean;
  isStale?: boolean;
}

export function useTargetTriageActions({
  targetId,
  targetStatus,
  latestCheck,
  currentSnapshot,
  hasReviewCandidate,
  isChecking,
  isStale = false,
}: UseTargetTriageActionsOptions) {
  const approveBaselineMutation = useApproveBaselineMutation();
  const acknowledgeCheckMutation = useAcknowledgeCheckMutation();
  const confirmDefacedMutation = useConfirmDefacedMutation();
  const [dismissedTriageKey, setDismissedTriageKey] = useState<string | null>(null);
  const [errorState, setErrorState] = useState<{ key: string | null; message: string } | null>(null);

  const triageKey = latestCheck?.id ?? currentSnapshot?.id ?? null;
  const error = errorState?.key === triageKey ? errorState.message : null;
  const isPending =
    approveBaselineMutation.isPending ||
    acknowledgeCheckMutation.isPending ||
    confirmDefacedMutation.isPending;
  const isResolved = Boolean(
    (triageKey && dismissedTriageKey === triageKey) ||
    latestCheck?.acknowledged_at ||
    targetStatus === 'Defaced' ||
    currentSnapshot?.is_baseline
  );

  const canApproveBaseline = Boolean(
    !isStale &&
    !isResolved &&
    hasReviewCandidate &&
    currentSnapshot &&
    !currentSnapshot.is_baseline &&
    currentSnapshot.id !== latestCheck?.baseline_snapshot_id
  );
  const canAcknowledge = Boolean(
    !isStale && !isResolved && latestCheck?.status === 'Changed' && !latestCheck.acknowledged_at
  );
  const canConfirmDefacement = Boolean(
    !isStale && !isResolved && latestCheck?.status === 'Changed' && targetStatus !== 'Defaced'
  );

  const finishAction = () => {
    if (triageKey) setDismissedTriageKey(triageKey);
    setErrorState(null);
  };

  const handleApproveBaseline = async () => {
    if (!currentSnapshot) return;
    setErrorState(null);
    try {
      await approveBaselineMutation.mutateAsync({ targetId, snapshotId: currentSnapshot.id });
      finishAction();
    } catch (err) {
      console.error('Failed to approve baseline:', err);
      setErrorState({ key: triageKey, message: err instanceof Error ? err.message : 'Failed to approve baseline' });
    }
  };

  const handleAcknowledge = async () => {
    if (!latestCheck) return;
    setErrorState(null);
    try {
      await acknowledgeCheckMutation.mutateAsync({ targetId, checkId: latestCheck.id });
      finishAction();
    } catch (err) {
      console.error('Failed to acknowledge check:', err);
      setErrorState({ key: triageKey, message: err instanceof Error ? err.message : 'Failed to acknowledge check' });
    }
  };

  const handleConfirmDefacement = async () => {
    if (!latestCheck) return;
    setErrorState(null);
    try {
      await confirmDefacedMutation.mutateAsync({ targetId, checkId: latestCheck.id });
      finishAction();
    } catch (err) {
      console.error('Failed to confirm defacement:', err);
      setErrorState({ key: triageKey, message: err instanceof Error ? err.message : 'Failed to confirm defacement' });
    }
  };

  return {
    canApproveBaseline,
    canAcknowledge,
    canConfirmDefacement,
    isPending,
    isChecking,
    isResolved,
    isStale,
    wasActionSubmitted: Boolean(triageKey && dismissedTriageKey === triageKey),
    error,
    dismissError: () => setErrorState(null),
    handleApproveBaseline,
    handleAcknowledge,
    handleConfirmDefacement,
    approveIsPending: approveBaselineMutation.isPending,
    acknowledgeIsPending: acknowledgeCheckMutation.isPending,
    confirmIsPending: confirmDefacedMutation.isPending,
  };
}

export type TargetTriageActions = ReturnType<typeof useTargetTriageActions>;
