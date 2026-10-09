import { apiFetch } from './client';
import type { PaginatedTags, Tag, TagPayload } from '../types/tag';
import type { PaginatedTargets } from '../types/target';

export async function listTags(search = '', limit = 200, offset = 0): Promise<PaginatedTags> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (search.trim()) params.set('search', search.trim());
  return apiFetch<PaginatedTags>(`/tags?${params.toString()}`);
}

export async function createTag(payload: TagPayload): Promise<Tag> {
  return apiFetch<Tag>('/tags', { method: 'POST', body: JSON.stringify(payload) });
}

export async function updateTag(tagId: string, payload: Partial<TagPayload>): Promise<Tag> {
  return apiFetch<Tag>(`/tags/${tagId}`, { method: 'PATCH', body: JSON.stringify(payload) });
}

export async function deleteTag(tagId: string): Promise<void> {
  await apiFetch(`/tags/${tagId}`, { method: 'DELETE' });
}

export async function listTagTargets(tagId: string, limit = 20, offset = 0): Promise<PaginatedTargets> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    include_inactive: 'false',
    tag_match: 'any',
  });
  params.append('tag_ids', tagId);
  return apiFetch<PaginatedTargets>(`/targets/page?${params.toString()}`);
}

export async function removeTagFromTarget(targetId: string, tagId: string): Promise<void> {
  await apiFetch(`/targets/${targetId}/tags/${tagId}`, { method: 'DELETE' });
}
