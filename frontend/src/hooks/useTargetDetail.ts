import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getTarget } from '../api/targets';
import { listTargetSnapshots, getTargetBaselineSnapshot, listTargetBaselines, demoteTargetBaseline } from '../api/snapshots';
import { listTargetChecks, acknowledgeCheck, confirmDefacedCheck, getCheck } from '../api/checks';
import { approveBaseline } from '../api/review';
import { getConfig } from '../api/config';

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
      queryClient.invalidateQueries({ queryKey: ['targets', targetId] });
      queryClient.invalidateQueries({ queryKey: ['snapshots', targetId] });
      queryClient.invalidateQueries({ queryKey: ['baseline', targetId] });
      queryClient.invalidateQueries({ queryKey: ['baselines', targetId] });
      queryClient.invalidateQueries({ queryKey: ['checks', targetId] });
      // Proactive refetch
      queryClient.refetchQueries({ queryKey: ['targets', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['snapshots', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['baseline', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['baselines', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['checks', targetId], type: 'active' });
    },
  });
}

export function useDemoteBaselineMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetId, snapshotId }: { targetId: string; snapshotId: string }) =>
      demoteTargetBaseline(targetId, snapshotId),
    onSuccess: (_, { targetId }) => {
      queryClient.invalidateQueries({ queryKey: ['targets', targetId] });
      queryClient.invalidateQueries({ queryKey: ['snapshots', targetId] });
      queryClient.invalidateQueries({ queryKey: ['baseline', targetId] });
      queryClient.invalidateQueries({ queryKey: ['baselines', targetId] });
      queryClient.invalidateQueries({ queryKey: ['checks', targetId] });
      // Proactive refetch
      queryClient.refetchQueries({ queryKey: ['targets', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['snapshots', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['baseline', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['baselines', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['checks', targetId], type: 'active' });
    },
  });
}

export function useAcknowledgeCheckMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ checkId }: { targetId: string; checkId: string }) =>
      acknowledgeCheck(checkId),
    onSuccess: (_, { targetId }) => {
      queryClient.invalidateQueries({ queryKey: ['targets', targetId] });
      queryClient.invalidateQueries({ queryKey: ['snapshots', targetId] });
      queryClient.invalidateQueries({ queryKey: ['baseline', targetId] });
      queryClient.invalidateQueries({ queryKey: ['checks', targetId] });
      // Proactive refetch
      queryClient.refetchQueries({ queryKey: ['targets', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['snapshots', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['baseline', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['checks', targetId], type: 'active' });
    },
  });
}

export function useConfirmDefacedMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ checkId }: { targetId: string; checkId: string }) =>
      confirmDefacedCheck(checkId),
    onSuccess: (_, { targetId }) => {
      queryClient.invalidateQueries({ queryKey: ['targets', targetId] });
      queryClient.invalidateQueries({ queryKey: ['snapshots', targetId] });
      queryClient.invalidateQueries({ queryKey: ['baseline', targetId] });
      queryClient.invalidateQueries({ queryKey: ['checks', targetId] });
      // Proactive refetch
      queryClient.refetchQueries({ queryKey: ['targets', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['snapshots', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['baseline', targetId], type: 'active' });
      queryClient.refetchQueries({ queryKey: ['checks', targetId], type: 'active' });
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
