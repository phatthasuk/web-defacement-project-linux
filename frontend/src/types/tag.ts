export type TagColor = 'cyan' | 'blue' | 'violet' | 'emerald' | 'amber' | 'rose' | 'slate';

export interface Tag {
  id: string;
  name: string;
  color_key: TagColor;
  parent_id: string | null;
  parent_name: string | null;
  target_count: number;
  created_at: string;
  updated_at: string;
}

export interface TagPayload {
  name: string;
  color_key: TagColor;
  parent_id?: string | null;
}

export interface PaginatedTags {
  items: Tag[];
  total: number;
  limit: number;
  offset: number;
}
