import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ScreenshotPreviewModal } from './ScreenshotPreviewModal';
import type { CheckResult } from '../types/checkResult';
import type { Snapshot } from '../types/snapshot';
import type { Target } from '../types/target';

const mocks = vi.hoisted(() => ({
  useTargetQuery: vi.fn(),
  useTargetSnapshotsQuery: vi.fn(),
  useTargetBaselineSnapshotQuery: vi.fn(),
  useTargetChecksQuery: vi.fn(),
  useApproveBaselineMutation: vi.fn(),
  useAcknowledgeCheckMutation: vi.fn(),
  useConfirmDefacedMutation: vi.fn(),
  approve: vi.fn(),
  acknowledge: vi.fn(),
  confirm: vi.fn(),
}));

vi.mock('../hooks/useTargetDetail', () => ({
  useTargetQuery: mocks.useTargetQuery,
  useTargetSnapshotsQuery: mocks.useTargetSnapshotsQuery,
  useTargetBaselineSnapshotQuery: mocks.useTargetBaselineSnapshotQuery,
  useTargetChecksQuery: mocks.useTargetChecksQuery,
  useApproveBaselineMutation: mocks.useApproveBaselineMutation,
  useAcknowledgeCheckMutation: mocks.useAcknowledgeCheckMutation,
  useConfirmDefacedMutation: mocks.useConfirmDefacedMutation,
}));

vi.mock('./ScreenshotCompare', () => ({
  ScreenshotCompare: ({ baselineSnapshotId, currentSnapshotId }: {
    baselineSnapshotId?: string | null;
    currentSnapshotId?: string | null;
  }) => (
    <div data-testid="screenshot-comparison">
      {baselineSnapshotId}:{currentSnapshotId}
    </div>
  ),
}));

const target: Target = {
  id: 'target-1',
  name: 'Production Gateway',
  url: 'https://example.com',
  url_revision: 1,
  status: 'Changed',
  is_active: true,
  last_error: null,
  created_at: '2026-07-02T00:00:00Z',
  updated_at: '2026-07-02T01:00:00Z',
};

const baseline: Snapshot = {
  id: 'snap-baseline',
  target_id: target.id,
  url_revision: 1,
  captured_at: '2026-07-02T01:00:00Z',
  final_url: target.url,
  http_status: 200,
  title: 'Home Page',
  is_baseline: true,
};

const current: Snapshot = {
  ...baseline,
  id: 'snap-current',
  captured_at: '2026-07-02T02:00:00Z',
  is_baseline: false,
};

const changedCheck: CheckResult = {
  id: 'check-1',
  target_id: target.id,
  baseline_snapshot_id: baseline.id,
  current_snapshot_id: current.id,
  created_at: '2026-07-02T02:00:00Z',
  status: 'Changed',
  text_change_score: 0.05,
  visual_change_score: 0.02,
  structure_change_score: 0,
  summary: 'Visual change detected.',
  acknowledged_at: null,
};

let activeSnapshots: Snapshot[];
let activeChecks: CheckResult[];

describe('ScreenshotPreviewModal triage actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    activeSnapshots = [current, baseline];
    activeChecks = [changedCheck];
    mocks.approve.mockResolvedValue({ ...current, is_baseline: true });
    mocks.acknowledge.mockResolvedValue(changedCheck);
    mocks.confirm.mockResolvedValue(changedCheck);
    mocks.useTargetQuery.mockReturnValue({ data: target });
    mocks.useTargetSnapshotsQuery.mockImplementation(() => ({ data: activeSnapshots, isLoading: false, isError: false }));
    mocks.useTargetBaselineSnapshotQuery.mockReturnValue({ data: baseline, isLoading: false, isError: false });
    mocks.useTargetChecksQuery.mockImplementation(() => ({ data: activeChecks, isLoading: false, isError: false }));
    mocks.useApproveBaselineMutation.mockReturnValue({ mutateAsync: mocks.approve, isPending: false });
    mocks.useAcknowledgeCheckMutation.mockReturnValue({ mutateAsync: mocks.acknowledge, isPending: false });
    mocks.useConfirmDefacedMutation.mockReturnValue({ mutateAsync: mocks.confirm, isPending: false });
  });

  it('shows the review actions in Preview and closes all actions after one succeeds', async () => {
    render(<ScreenshotPreviewModal target={target} onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Approve as Baseline' }));

    await waitFor(() => expect(mocks.approve).toHaveBeenCalledWith({
      targetId: target.id,
      snapshotId: current.id,
    }));
    expect(await screen.findByText(/Status saved/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approve as Baseline/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Acknowledge Change/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Confirm Defacement/i })).not.toBeInTheDocument();
  });

  it('keeps actions available after a failed decision so it can be retried', async () => {
    mocks.approve.mockRejectedValueOnce(new Error('Approval failed'));
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(<ScreenshotPreviewModal target={target} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Approve as Baseline' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Approval failed');
    expect(screen.getByRole('button', { name: 'Approve as Baseline' })).toBeInTheDocument();
    consoleError.mockRestore();
  });

  it('disables every status action while a check is in progress', async () => {
    mocks.useTargetQuery.mockReturnValue({ data: { ...target, status: 'Checking' } });

    render(<ScreenshotPreviewModal target={target} onClose={vi.fn()} />);

    expect(await screen.findByText(/A check is in progress/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Approve as Baseline/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Acknowledge Change/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /Confirm Defacement/i })).toBeDisabled();
  });

  it('requires loading a newer comparison before it enables actions for that check', async () => {
    const { rerender } = render(<ScreenshotPreviewModal target={target} onClose={vi.fn()} />);
    expect(await screen.findByRole('button', { name: 'Approve as Baseline' })).toBeInTheDocument();

    const nextSnapshot: Snapshot = { ...current, id: 'snap-current-2', captured_at: '2026-07-02T03:00:00Z' };
    const nextCheck: CheckResult = {
      ...changedCheck,
      id: 'check-2',
      current_snapshot_id: nextSnapshot.id,
      created_at: '2026-07-02T03:00:00Z',
    };
    activeSnapshots = [nextSnapshot, current, baseline];
    activeChecks = [nextCheck, changedCheck];
    rerender(<ScreenshotPreviewModal target={target} onClose={vi.fn()} />);

    expect(await screen.findByText(/A newer check is available/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approve as Baseline/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load latest comparison' }));

    expect(await screen.findByRole('button', { name: 'Approve as Baseline' })).toBeInTheDocument();
    expect(screen.getByTestId('screenshot-comparison')).toHaveTextContent('snap-baseline:snap-current-2');
  });
});
