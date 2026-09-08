export interface Snapshot {
  id: string;
  target_id: string;
  captured_at: string;
  final_url: string;
  http_status: number | null;
  title: string | null;
  is_baseline: boolean;
}
