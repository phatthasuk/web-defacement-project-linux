import { apiFetch } from './client';
import { PaginatedTargets, Target, TargetCreatePayload, TargetUpdatePayload } from '../types/target';

export interface CheckTriggerResponse {
  target_id: string;
  accepted: boolean;
}

export async function listTargets(includeInactive: boolean = false): Promise<Target[]> {
  const query = includeInactive ? '?include_inactive=true' : '';
  return apiFetch<Target[]>(`/targets${query}`);
}

export async function getPaginatedTargets(
  limit: number = 50,
  offset: number = 0,
  includeInactive: boolean = false,
  tagIds: string[] = [],
  tagMatch: 'any' | 'all' = 'any',
  status?: string,
  sortBy?: 'status' | 'last_activity',
  sortOrder: 'asc' | 'desc' = 'desc'
): Promise<PaginatedTargets> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
    include_inactive: includeInactive.toString(),
    tag_match: tagMatch,
  });
  if (status) params.set('status', status);
  if (sortBy) params.set('sort_by', sortBy);
  if (sortBy) params.set('sort_order', sortOrder);
  tagIds.forEach((tagId) => params.append('tag_ids', tagId));
  return apiFetch<PaginatedTargets>(`/targets/page?${params.toString()}`);
}

export async function createTarget(payload: TargetCreatePayload): Promise<Target> {
  return apiFetch<Target>('/targets', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updateTarget(targetId: string, payload: TargetUpdatePayload): Promise<Target> {
  return apiFetch<Target>(`/targets/${targetId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export async function deleteTarget(targetId: string): Promise<Target> {
  return apiFetch<Target>(`/targets/${targetId}`, {
    method: 'DELETE',
  });
}

export async function triggerCheck(targetId: string): Promise<CheckTriggerResponse> {
  return apiFetch<CheckTriggerResponse>(`/targets/${targetId}/check`, {
    method: 'POST',
  });
}

export async function getTarget(targetId: string): Promise<Target> {
  return apiFetch<Target>(`/targets/${targetId}`);
}
