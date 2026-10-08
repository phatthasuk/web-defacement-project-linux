import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createTag, deleteTag, listTags, updateTag } from '../api/tags';
import type { TagPayload } from '../types/tag';

export const TAGS_QUERY_KEY = ['tags'] as const;

export function useTagsQuery(search = '') {
  return useQuery({
    queryKey: [...TAGS_QUERY_KEY, { search }],
    queryFn: () => listTags(search),
  });
}

function useInvalidateTags() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: TAGS_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ['targets'] });
  };
}

export function useCreateTagMutation() {
  const invalidate = useInvalidateTags();
  return useMutation({ mutationFn: createTag, onSuccess: invalidate });
}

export function useUpdateTagMutation() {
  const invalidate = useInvalidateTags();
  return useMutation({
    mutationFn: ({ tagId, payload }: { tagId: string; payload: Partial<TagPayload> }) => updateTag(tagId, payload),
    onSuccess: invalidate,
  });
}

export function useDeleteTagMutation() {
  const invalidate = useInvalidateTags();
  return useMutation({ mutationFn: deleteTag, onSuccess: invalidate });
}
