import { useQuery, useMutation, useQueryClient, QueryClient } from '@tanstack/react-query';
import { getTarget } from '../api/targets';
import {
  demoteTargetBaseline,
  getSnapshot,
  getTargetBaselineSnapshot,
  listTargetBaselines,
  listTargetSnapshots,
} from '../api/snapshots';
import type { Snapshot } from '../types/snapshot';
import { listTargetChecks, acknowledgeCheck, confirmDefacedCheck, getCheck } from '../api/checks';
import { approveBaseline } from '../api/review';
import { getConfig } from '../api/config';

export const TARGET_DETAIL_QUERY_KEYS = {
  root: ['targets'] as const,
  detail: (targetId: string) => ['targets', targetId] as const,
  snapshots: (targetId: string) => ['snapshots', targetId] as const,
  baseline: (targetId: string) => ['baseline', targetId] as const,
  baselines: (targetId: string) => ['baselines', targetId] as const,
  checks: (targetId: string) => ['checks', targetId] as const,
  check: (checkId: string) => ['check', checkId] as const,
};

export function refreshTargetDetailQueries(
  queryClient: QueryClient,
  targetId: string,
  options: { includeBaselines?: boolean; invalidateRoot?: boolean } = {}
) {
  const { includeBaselines = false, invalidateRoot = true } = options;
  if (invalidateRoot) {
    queryClient.invalidateQueries({ queryKey: TARGET_DETAIL_QUERY_KEYS.root });
  }
  const keys = [
    TARGET_DETAIL_QUERY_KEYS.detail(targetId),
    TARGET_DETAIL_QUERY_KEYS.snapshots(targetId),
    TARGET_DETAIL_QUERY_KEYS.baseline(targetId),
    ...(includeBaselines ? [TARGET_DETAIL_QUERY_KEYS.baselines(targetId)] : []),
    TARGET_DETAIL_QUERY_KEYS.checks(targetId),
  ];
  for (const queryKey of keys) {
    queryClient.invalidateQueries({ queryKey });
  }
  for (const queryKey of keys) {
    queryClient.refetchQueries({ queryKey, type: 'active' });
  }
}

export function useConfigQuery() {
  return useQuery({
    queryKey: ['config'],
    queryFn: getConfig,
    staleTime: Infinity,
  });
}

export function useTargetQuery(targetId: string) {
  return useQuery({
    queryKey: ['targets', targetId],
    queryFn: () => getTarget(targetId),
    enabled: !!targetId,
    refetchInterval: (query) => (query.state.data?.status === 'Checking' ? 3000 : 4000),
  });
}

export function useTargetSnapshotsQuery(targetId: string) {
  return useQuery({
    queryKey: ['snapshots', targetId],
    queryFn: () => listTargetSnapshots(targetId),
    enabled: !!targetId,
  });
}

export function useSnapshotQuery(snapshotId?: string, initialData?: Snapshot) {
  return useQuery({
    queryKey: ['snapshot', snapshotId],
    queryFn: () => getSnapshot(snapshotId!),
    enabled: !!snapshotId,
    initialData,
  });
}

export function useTargetBaselineSnapshotQuery(targetId: string) {
  return useQuery({
    queryKey: ['baseline', targetId],
    queryFn: () => getTargetBaselineSnapshot(targetId),
    enabled: !!targetId,
  });
}

export function useTargetBaselinesQuery(targetId: string) {
  return useQuery({
    queryKey: ['baselines', targetId],
    queryFn: () => listTargetBaselines(targetId),
    enabled: !!targetId,
  });
}

export function useTargetChecksQuery(targetId: string) {
  return useQuery({
    queryKey: ['checks', targetId],
    queryFn: () => listTargetChecks(targetId),
    enabled: !!targetId,
    refetchInterval: 4000,
  });
}

export function useApproveBaselineMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetId, snapshotId }: { targetId: string; snapshotId: string }) =>
      approveBaseline(targetId, snapshotId),
    onSuccess: (_, { targetId }) => {
      refreshTargetDetailQueries(queryClient, targetId, { includeBaselines: true, invalidateRoot: true });
    },
  });
}

export function useDemoteBaselineMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetId, snapshotId }: { targetId: string; snapshotId: string }) =>
      demoteTargetBaseline(targetId, snapshotId),
    onSuccess: (_, { targetId }) => {
      refreshTargetDetailQueries(queryClient, targetId, { includeBaselines: true, invalidateRoot: true });
    },
  });
}

export function useAcknowledgeCheckMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ checkId }: { targetId: string; checkId: string }) =>
      acknowledgeCheck(checkId),
    onSuccess: (_, { targetId }) => {
      refreshTargetDetailQueries(queryClient, targetId, { includeBaselines: false, invalidateRoot: true });
    },
  });
}

export function useConfirmDefacedMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ checkId }: { targetId: string; checkId: string }) =>
      confirmDefacedCheck(checkId),
    onSuccess: (_, { targetId }) => {
      refreshTargetDetailQueries(queryClient, targetId, { includeBaselines: false, invalidateRoot: true });
    },
  });
}

export function useCheckQuery(checkId: string) {
  return useQuery({
    queryKey: ['check', checkId],
    queryFn: () => getCheck(checkId),
    enabled: !!checkId,
  });
}
