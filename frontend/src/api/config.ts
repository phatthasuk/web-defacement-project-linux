import { apiFetch } from './client';

export interface AppConfig {
  text_change_threshold: number;
  structure_change_threshold: number;
  visual_change_threshold: number;
  max_baselines_per_target?: number;
}

export async function getConfig(): Promise<AppConfig> {
  return apiFetch<AppConfig>('/config');
}
