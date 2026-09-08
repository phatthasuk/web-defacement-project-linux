import { apiFetch } from './client';
import { Snapshot } from '../types/snapshot';

export async function listTargetSnapshots(targetId: string): Promise<Snapshot[]> {
  return apiFetch<Snapshot[]>(`/targets/${targetId}/snapshots`);
}

export async function getSnapshotText(snapshotId: string): Promise<string> {
  return apiFetch<string>(`/snapshots/${snapshotId}/text`);
}

export async function getTargetBaselineSnapshot(targetId: string): Promise<Snapshot | null> {
  return apiFetch<Snapshot | null>(`/targets/${targetId}/baseline`);
}

export async function listTargetBaselines(targetId: string): Promise<Snapshot[]> {
  return apiFetch<Snapshot[]>(`/targets/${targetId}/baselines`);
}

export async function demoteTargetBaseline(targetId: string, snapshotId: string): Promise<Snapshot> {
  return apiFetch<Snapshot>(`/targets/${targetId}/baselines/${snapshotId}/demote`, {
    method: 'POST',
  });
}

