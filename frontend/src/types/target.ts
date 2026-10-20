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

export interface CheckProgressStep {
  phase: string;
  state: 'running' | 'completed' | 'skipped' | 'failed' | 'retry_wait';
  started_at: string;
  finished_at: string | null;
}

export interface CheckProgress {
  run_id: string;
  url_revision: number;
  attempt_number: number;
  phase: string;
  state: 'queued' | 'running' | 'retry_wait' | 'finished';
  attempt_started_at: string;
  phase_started_at: string;
  updated_at: string;
  finished_at: string | null;
  outcome: string | null;
  error_code: string | null;
  steps: CheckProgressStep[];
}

export interface Target {
  id: string;
  name: string;
  url: string;
  url_revision: number;
  status: TargetStatus;
  is_active: boolean;
  last_error: string | null;
  last_error_code?: string | null;
  last_http_status?: number | null;
  next_check_at?: string | null;
  check_run_id?: string | null;
  check_run_source?: string | null;
  check_attempt_count?: number;
  check_retry_max_attempts?: number;
  check_progress?: CheckProgress | null;
  latest_structure_change_score?: number | null;
  tags?: Tag[];
  assignees?: { id:number; username:string; display_name:string; is_active:boolean }[] | null;
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

