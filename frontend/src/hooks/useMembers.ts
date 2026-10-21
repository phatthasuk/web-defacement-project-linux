import { useMutation, useQuery, useQueryClient, QueryClient } from '@tanstack/react-query';
import {
  approveMember,
  assignMemberWebsite,
  createMember,
  getMember,
  listAssignmentWebsites,
  listMembers,
  listMemberWebsites,
  rejectMember,
  removeMemberWebsiteAssignment,
  resetMemberPassword,
  updateMember,
} from '../api/members';
import type {
  MemberCreatePayload,
  MemberUpdatePayload,
  RejectMemberPayload,
  ResetPasswordPayload,
} from '../types/member';

export const MEMBERS_QUERY_KEY = ['members'] as const;
export const MEMBER_ASSIGNMENTS_QUERY_KEY = ['member-assignments'] as const;
export const MEMBER_WEBSITES_QUERY_KEY = ['member-websites'] as const;

export function invalidateMemberCaches(queryClient: QueryClient, memberId?: number) {
  queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
  queryClient.invalidateQueries({ queryKey: MEMBER_ASSIGNMENTS_QUERY_KEY });
  queryClient.invalidateQueries({ queryKey: ['targets'] });
  queryClient.invalidateQueries({ queryKey: ['tags'] });
  if (memberId !== undefined) {
    queryClient.invalidateQueries({ queryKey: [...MEMBERS_QUERY_KEY, memberId] });
    queryClient.invalidateQueries({ queryKey: [...MEMBER_WEBSITES_QUERY_KEY, memberId] });
  }
}

export function useMembersQuery(params?: {
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: [...MEMBERS_QUERY_KEY, params],
    queryFn: () => listMembers(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useMemberQuery(id?: number) {
  return useQuery({
    queryKey: [...MEMBERS_QUERY_KEY, id],
    queryFn: () => getMember(id!),
    enabled: typeof id === 'number' && !isNaN(id),
  });
}

export function useMemberWebsitesQuery(memberId?: number, includeInactive = false) {
  return useQuery({
    queryKey: [...MEMBER_WEBSITES_QUERY_KEY, memberId, { includeInactive }],
    queryFn: () => listMemberWebsites(memberId!, includeInactive, 200),
    enabled: typeof memberId === 'number' && !isNaN(memberId),
  });
}

export function useAssignableWebsitesQuery(includeInactive = false, limit = 200) {
  return useQuery({
    queryKey: [...MEMBER_ASSIGNMENTS_QUERY_KEY, 'assignable', { includeInactive, limit }],
    queryFn: () => listAssignmentWebsites({ view: 'all', includeInactive, limit }),
  });
}

export function useAssignmentWebsitesQuery(params?: {
  view?: string;
  search?: string;
  operatorId?: string;
  tagIds?: string[];
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
}) {
  return useQuery({
    queryKey: [...MEMBER_ASSIGNMENTS_QUERY_KEY, params],
    queryFn: () => listAssignmentWebsites(params),
    placeholderData: (previousData) => previousData,
  });
}

export function useCreateMemberMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MemberCreatePayload) => createMember(payload),
    onSuccess: () => {
      invalidateMemberCaches(queryClient);
    },
  });
}

export function useApproveMemberMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (memberId: number) => approveMember(memberId),
    onSuccess: (data) => {
      invalidateMemberCaches(queryClient, data.id);
    },
  });
}

export function useRejectMemberMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memberId, payload }: { memberId: number; payload?: RejectMemberPayload }) =>
      rejectMember(memberId, payload),
    onSuccess: (data) => {
      invalidateMemberCaches(queryClient, data.id);
    },
  });
}

export function useUpdateMemberMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memberId, payload }: { memberId: number; payload: MemberUpdatePayload }) =>
      updateMember(memberId, payload),
    onSuccess: (data) => {
      invalidateMemberCaches(queryClient, data.id);
    },
  });
}

export function useResetMemberPasswordMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memberId, payload }: { memberId: number; payload: ResetPasswordPayload }) =>
      resetMemberPassword(memberId, payload),
    onSuccess: (_data, variables) => {
      invalidateMemberCaches(queryClient, variables.memberId);
    },
  });
}

export function useAssignMemberWebsiteMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memberId, targetId }: { memberId: number; targetId: string }) =>
      assignMemberWebsite(memberId, targetId),
    onSuccess: (_data, variables) => {
      invalidateMemberCaches(queryClient, variables.memberId);
    },
  });
}

export function useUnassignMemberWebsiteMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ memberId, targetId }: { memberId: number; targetId: string }) =>
      removeMemberWebsiteAssignment(memberId, targetId),
    onSuccess: (_data, variables) => {
      invalidateMemberCaches(queryClient, variables.memberId);
    },
  });
}
