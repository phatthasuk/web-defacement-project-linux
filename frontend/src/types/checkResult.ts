export interface CheckResult {
  id: string;
  target_id: string;
  baseline_snapshot_id: string;
  current_snapshot_id: string;
  created_at: string;
  status: string;
  text_change_score: number;
  visual_change_score: number;
  structure_change_score: number;
  summary: string;
  acknowledged_at: string | null;
}
