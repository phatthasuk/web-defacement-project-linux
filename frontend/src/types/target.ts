export type TargetStatus =
  | 'Never Checked'
  | 'Checking'
  | 'Awaiting Baseline'
  | 'OK'
  | 'Changed'
  | 'Failed'
  | 'Acknowledged'
  | 'Availability Issue'
  | 'Defaced';

import type { Tag } from './tag';

export interface Target {
  id: string;
  name: string;
  url: string;
  url_revision: number;
  status: TargetStatus;
  is_active: boolean;
  last_error: string | null;
  tags?: Tag[];
  created_at: string;
  updated_at: string;
}

export interface TargetCreatePayload {
  name: string;
  url: string;
  tag_ids?: string[];
}

export interface TargetUpdatePayload {
  name?: string;
  url?: string;
  is_active?: boolean;
  allowed_domains?: string[] | null;
  tag_ids?: string[];
}

export interface PaginatedTargets {
  items: Target[];
  total: number;
  limit: number;
  offset: number;
}

