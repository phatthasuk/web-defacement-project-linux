export type TagColor = 'cyan' | 'blue' | 'violet' | 'emerald' | 'amber' | 'rose' | 'slate';

export interface Tag {
  id: string;
  name: string;
  color_key: TagColor;
  target_count: number;
  created_at: string;
  updated_at: string;
}

export interface TagPayload {
  name: string;
  color_key: TagColor;
}

export interface PaginatedTags {
  items: Tag[];
  total: number;
  limit: number;
  offset: number;
}
