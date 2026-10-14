import { describe, expect, it } from 'vitest';
import { getScreenshotComparisonIds } from './screenshotComparison';
import type { Snapshot } from '../types/snapshot';
import type { Target } from '../types/target';

describe('getScreenshotComparisonIds', () => {
  it.each([1, 2])('shows an unapproved candidate on URL revision %i', (revision) => {
    const target: Target = {
      id: 'target-1', name: 'Example', url: 'https://example.com',
      url_revision: revision, status: 'Awaiting Baseline', is_active: true,
      last_error: null, created_at: '', updated_at: '',
    };
    const candidate: Snapshot = {
      id: 'candidate-1', target_id: target.id, url_revision: revision,
      captured_at: '', final_url: target.url, http_status: 200, title: 'Example',
      is_baseline: false,
    };

    expect(getScreenshotComparisonIds(target, [candidate], null, [])).toEqual({
      baselineSnapshotId: undefined,
      currentSnapshotId: candidate.id,
    });
  });
});
