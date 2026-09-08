import { apiFetch } from './client';
import { Snapshot } from '../types/snapshot';

export async function approveBaseline(targetId: string, snapshotId: string): Promise<Snapshot> {
  return apiFetch<Snapshot>(`/targets/${targetId}/baseline/approve`, {
    method: 'POST',
    body: JSON.stringify({ snapshot_id: snapshotId }),
  });
}
