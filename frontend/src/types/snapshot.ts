export interface Snapshot {
  id: string;
  target_id: string;
  url_revision: number;
  captured_at: string;
  final_url: string;
  http_status: number | null;
  title: string | null;
  is_baseline: boolean;
  viewport_width?: number | null;
  document_width?: number | null;
  screenshot_format_version?: number | null;
}
