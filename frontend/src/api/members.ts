import { apiFetch } from './client';
import type {
  Member,
  MemberCreatePayload,
  MemberUpdatePayload,
  MemberWebsitesList,
  PaginatedMembers,
  PaginatedMemberWebsites,
  RejectMemberPayload,
  ResetPasswordPayload,
} from '../types/member';

export async function listMembers(params?: {
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedMembers> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  if (params?.status) query.set('status', params.status);
  if (params?.search) query.set('search', params.search);
  const qs = query.toString();
  return apiFetch<PaginatedMembers>(qs ? `/members?${qs}` : '/members');
}

export async function getMember(id: number): Promise<Member> {
  return apiFetch<Member>(`/members/${id}`);
}

export async function createMember(payload: MemberCreatePayload): Promise<Member> {
  return apiFetch<Member>('/members', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function approveMember(id: number): Promise<Member> {
  return apiFetch<Member>(`/members/${id}/approve`, {
    method: 'POST',
  });
}

export async function rejectMember(id: number, payload?: RejectMemberPayload): Promise<Member> {
  return apiFetch<Member>(`/members/${id}/reject`, {
    method: 'POST',
    body: payload ? JSON.stringify(payload) : undefined,
  });
}

export async function updateMember(id: number, payload: MemberUpdatePayload): Promise<Member> {
  return apiFetch<Member>(`/members/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function resetMemberPassword(id: number, payload: ResetPasswordPayload): Promise<void> {
  return apiFetch<void>(`/members/${id}/reset-password`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function listMemberWebsites(
  memberId: number,
  includeInactive = false,
  limit = 50,
  offset = 0
): Promise<MemberWebsitesList> {
  const query = new URLSearchParams({
    include_inactive: String(includeInactive),
    limit: String(limit),
    offset: String(offset),
  });
  return apiFetch<MemberWebsitesList>(`/members/${memberId}/websites?${query}`);
}

export async function assignMemberWebsite(memberId: number, targetId: string): Promise<void> {
  return apiFetch<void>(`/members/${memberId}/websites/${targetId}`, {
    method: 'PUT',
  });
}

export async function removeMemberWebsiteAssignment(memberId: number, targetId: string): Promise<void> {
  return apiFetch<void>(`/members/${memberId}/websites/${targetId}`, {
    method: 'DELETE',
  });
}

export async function listAssignmentWebsites(params?: {
  view?: string;
  search?: string;
  operatorId?: string;
  tagIds?: string[];
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
}): Promise<PaginatedMemberWebsites> {
  const query = new URLSearchParams();
  if (params?.view) query.set('view', params.view);
  if (params?.search) query.set('search', params.search);
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  if (params?.includeInactive !== undefined) query.set('include_inactive', String(params.includeInactive));
  if (params?.operatorId) query.set('operator_id', params.operatorId);
  if (params?.tagIds) {
    for (const tagId of params.tagIds) {
      query.append('tag_ids', tagId);
    }
  }
  const qs = query.toString();
  return apiFetch<PaginatedMemberWebsites>(qs ? `/member-assignments/websites?${qs}` : '/member-assignments/websites');
}
