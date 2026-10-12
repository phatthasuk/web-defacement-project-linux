import type { CheckResult } from '../types/checkResult';
import type { Snapshot } from '../types/snapshot';
import type { Target } from '../types/target';

export function getScreenshotComparisonIds(
  target: Target | null | undefined,
  snapshots: Snapshot[] | undefined,
  baselineSnapshot: Snapshot | null | undefined,
  checks: CheckResult[] | undefined,
) {
  const latestCheck = checks?.[0];
  const latestSnapshot = snapshots?.[0] ?? null;
  const pendingCandidate = target && target.url_revision > 1 && !baselineSnapshot && !latestCheck
    ? latestSnapshot
    : null;

  return {
    baselineSnapshotId: latestCheck?.baseline_snapshot_id || baselineSnapshot?.id,
    currentSnapshotId: latestCheck?.current_snapshot_id || pendingCandidate?.id || baselineSnapshot?.id,
  };
}
