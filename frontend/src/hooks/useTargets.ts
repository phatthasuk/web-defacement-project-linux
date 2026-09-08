import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listTargets, getPaginatedTargets, createTarget, updateTarget, deleteTarget, triggerCheck } from '../api/targets';
import { TargetCreatePayload, TargetUpdatePayload } from '../types/target';

export const TARGETS_QUERY_KEY = ['targets'] as const;

export function useTargetsQuery(includeInactive: boolean = false) {
  return useQuery({
    queryKey: [...TARGETS_QUERY_KEY, { includeInactive }],
    queryFn: () => listTargets(includeInactive),
    refetchInterval: 4000, // Poll every 4 seconds
  });
}

export function usePaginatedTargetsQuery(
  limit: number = 50,
  offset: number = 0,
  includeInactive: boolean = false
) {
  return useQuery({
    queryKey: [...TARGETS_QUERY_KEY, 'page', { limit, offset, includeInactive }],
    queryFn: () => getPaginatedTargets(limit, offset, includeInactive),
    refetchInterval: 4000,
  });
}

export function useCreateTargetMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TargetCreatePayload) => createTarget(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TARGETS_QUERY_KEY });
      queryClient.refetchQueries({ queryKey: TARGETS_QUERY_KEY, type: 'active' });
    },
  });
}

export function useUpdateTargetMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetId, payload }: { targetId: string; payload: TargetUpdatePayload }) =>
      updateTarget(targetId, payload),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: TARGETS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ['targets', variables.targetId] });
      queryClient.refetchQueries({ queryKey: TARGETS_QUERY_KEY, type: 'active' });
    },
  });
}

export function useDeleteTargetMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetId: string) => deleteTarget(targetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TARGETS_QUERY_KEY });
      queryClient.refetchQueries({ queryKey: TARGETS_QUERY_KEY, type: 'active' });
    },
  });
}

export function useTriggerCheckMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetId: string) => triggerCheck(targetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TARGETS_QUERY_KEY });
      queryClient.refetchQueries({ queryKey: TARGETS_QUERY_KEY, type: 'active' });
    },
  });
}
