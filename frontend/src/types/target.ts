export type TargetStatus =
  | 'Never Checked'
  | 'Checking'
  | 'OK'
  | 'Changed'
  | 'Failed'
  | 'Acknowledged'
  | 'Availability Issue'
  | 'Defaced';

export interface Target {
  id: string;
  name: string;
  url: string;
  status: TargetStatus;
  is_active: boolean;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface TargetCreatePayload {
  name: string;
  url: string;
}

export interface TargetUpdatePayload {
  name?: string;
  url?: string;
  is_active?: boolean;
  allowed_domains?: string[] | null;
}

export interface PaginatedTargets {
  items: Target[];
  total: number;
  limit: number;
  offset: number;
}

