import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { useQuery } from '@tanstack/react-query';
import { TargetDetailPage } from './TargetDetailPage';
import * as useTargetDetailHooks from '../hooks/useTargetDetail';

// Mock the hooks
vi.mock('../hooks/useTargetDetail', () => ({
  useTargetQuery: vi.fn(),
  useTargetSnapshotsQuery: vi.fn(),
  useTargetBaselineSnapshotQuery: vi.fn(),
  useTargetBaselinesQuery: vi.fn(),
  useDemoteBaselineMutation: vi.fn(),
  useTargetChecksQuery: vi.fn(),
  useApproveBaselineMutation: vi.fn(),
  useAcknowledgeCheckMutation: vi.fn(),
  useConfirmDefacedMutation: vi.fn(),
  useConfigQuery: vi.fn(),
}));

vi.mock('../hooks/useTargets', () => ({
  useUpdateTargetMutation: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteTargetMutation: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false }),
}));

// Mock react-query useQuery for text diff fetching
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const original = await importOriginal<Record<string, unknown>>();
  return {
    ...original,
    useQuery: vi.fn().mockReturnValue({ data: 'Mock Snapshot Text Content', isLoading: false }),
    useQueryClient: () => ({
      invalidateQueries: vi.fn(),
      refetchQueries: vi.fn(),
    }),
  };
});

describe('TargetDetailPage', () => {
  const mockTarget = {
    id: 'target-1',
    name: 'Production Gateway',
    url: 'https://example.com',
    status: 'Changed',
    is_active: true,
    created_at: '2026-07-02T00:00:00Z',
    updated_at: '2026-07-02T01:00:00Z',
  };

  const mockSnapshots = [
    {
      id: 'snap-latest',
      target_id: 'target-1',
      captured_at: '2026-07-02T02:00:00Z',
      final_url: 'https://example.com',
      http_status: 200,
      title: 'Home Page',
      is_baseline: false,
    },
    {
      id: 'snap-baseline',
      target_id: 'target-1',
      captured_at: '2026-07-02T01:00:00Z',
      final_url: 'https://example.com',
      http_status: 200,
      title: 'Home Page',
      is_baseline: true,
    },
  ];

  const mockChecks = [
    {
      id: 'check-1',
      target_id: 'target-1',
      baseline_snapshot_id: 'snap-baseline',
      current_snapshot_id: 'snap-latest',
      status: 'Changed',
      text_change_score: 0.05,
      visual_change_score: 0.02,
      structure_change_score: 0,
      summary: 'Text content changed slightly.',
      created_at: '2026-07-02T02:00:00Z',
      acknowledged_at: null,
    },
  ];

  const mockMutateAsyncApprove = vi.fn();
  const mockMutateAsyncAcknowledge = vi.fn();
  const mockMutateAsyncConfirmDefaced = vi.fn();

  const useQueryMock = useQuery as unknown as Mock;

  /** Drive each snapshot-text query independently, keyed by snapshot id. */
  const mockTextQueries = (states: Record<string, Record<string, unknown>>) => {
    useQueryMock.mockImplementation((options: { queryKey?: unknown[]; enabled?: boolean }) => {
      const snapshotId = options.queryKey?.[1] as string | undefined;
      const base = {
        data: undefined,
        isLoading: false,
        isError: false,
        isFetching: false,
        refetch: vi.fn(),
      };
      if (options.enabled === false || !snapshotId) return base;
      return { ...base, ...states[snapshotId] };
    });
  };

  beforeEach(() => {
    vi.clearAllMocks();

    // Re-establish the default (both artifacts load fine).
    useQueryMock.mockReturnValue({
      data: 'Mock Snapshot Text Content',
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });

    vi.mocked(useTargetDetailHooks.useTargetQuery).mockReturnValue({
      data: mockTarget,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useTargetQuery>);

    vi.mocked(useTargetDetailHooks.useTargetSnapshotsQuery).mockReturnValue({
      data: mockSnapshots,
      isLoading: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useTargetSnapshotsQuery>);

    vi.mocked(useTargetDetailHooks.useTargetBaselineSnapshotQuery).mockReturnValue({
      data: mockSnapshots[1],
      isLoading: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useTargetBaselineSnapshotQuery>);

    vi.mocked(useTargetDetailHooks.useTargetBaselinesQuery).mockReturnValue({
      data: [mockSnapshots[1]],
      isLoading: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useTargetBaselinesQuery>);

    vi.mocked(useTargetDetailHooks.useTargetChecksQuery).mockReturnValue({
      data: mockChecks,
      isLoading: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useTargetChecksQuery>);

    vi.mocked(useTargetDetailHooks.useApproveBaselineMutation).mockReturnValue({
      mutateAsync: mockMutateAsyncApprove,
      isPending: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useApproveBaselineMutation>);

    vi.mocked(useTargetDetailHooks.useDemoteBaselineMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useDemoteBaselineMutation>);

    vi.mocked(useTargetDetailHooks.useAcknowledgeCheckMutation).mockReturnValue({
      mutateAsync: mockMutateAsyncAcknowledge,
      isPending: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useAcknowledgeCheckMutation>);

    vi.mocked(useTargetDetailHooks.useConfirmDefacedMutation).mockReturnValue({
      mutateAsync: mockMutateAsyncConfirmDefaced,
      isPending: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useConfirmDefacedMutation>);

    vi.mocked(useTargetDetailHooks.useConfigQuery).mockReturnValue({
      data: { text_change_threshold: 0.02, visual_change_threshold: 0.01, structure_change_threshold: 0.0 },
      isLoading: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useConfigQuery>);
  });

  it('renders target metadata, comparison info, and action buttons', () => {
    render(
      <BrowserRouter>
        <TargetDetailPage />
      </BrowserRouter>
    );

    expect(screen.getByText('Production Gateway')).toBeInTheDocument();
    expect(screen.getByText('https://example.com')).toBeInTheDocument();
    expect(screen.getByText('5.0%')).toBeInTheDocument(); // text score
    expect(screen.getByText('2.0%')).toBeInTheDocument(); // visual score
    expect(screen.getByRole('button', { name: /Approve as Baseline/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Acknowledge Change/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm Defacement/i })).toBeInTheDocument();
    expect(screen.getByText('View Full Details →')).toBeInTheDocument();
    expect(screen.getByText('View Full Details →').closest('a')).toHaveAttribute('href', '/checks/check-1');
  });

  it('calls approveBaseline when clicking Approve as Baseline button', async () => {
    render(
      <BrowserRouter>
        <TargetDetailPage />
      </BrowserRouter>
    );

    const approveBtn = screen.getByRole('button', { name: /Approve as Baseline/i });
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(mockMutateAsyncApprove).toHaveBeenCalledWith({
        targetId: 'target-1',
        snapshotId: 'snap-latest',
      });
    });
  });

  it('calls acknowledgeCheck when clicking Acknowledge Change button', async () => {
    render(
      <BrowserRouter>
        <TargetDetailPage />
      </BrowserRouter>
    );

    const ackBtn = screen.getByRole('button', { name: /Acknowledge Change/i });
    fireEvent.click(ackBtn);

    await waitFor(() => {
      expect(mockMutateAsyncAcknowledge).toHaveBeenCalledWith({
        targetId: 'target-1',
        checkId: 'check-1',
      });
    });
  });

  it('calls confirmDefacedCheck when clicking Confirm Defacement button', async () => {
    render(
      <BrowserRouter>
        <TargetDetailPage />
      </BrowserRouter>
    );

    const defacedBtn = screen.getByRole('button', { name: /Confirm Defacement/i });
    fireEvent.click(defacedBtn);

    await waitFor(() => {
      expect(mockMutateAsyncConfirmDefaced).toHaveBeenCalledWith({
        targetId: 'target-1',
        checkId: 'check-1',
      });
    });
  });

  // --- Artifact retrieval failures must never read as "unchanged" (Finding 4) ---

  it('reports an error, not "no differences", when a text artifact fails to load', () => {
    mockTextQueries({
      'snap-baseline': { isError: true },
      'snap-latest': { data: 'current content' },
    });

    render(
      <BrowserRouter>
        <TargetDetailPage />
      </BrowserRouter>
    );

    expect(screen.getByText('Text comparison unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Failed to load baseline text/i)).toBeInTheDocument();
    expect(screen.queryByText(/No textual differences detected/i)).not.toBeInTheDocument();
  });

  it('distinguishes successfully-empty artifacts from a failed request', () => {
    mockTextQueries({
      'snap-baseline': { data: '' },
      'snap-latest': { data: '' },
    });

    render(
      <BrowserRouter>
        <TargetDetailPage />
      </BrowserRouter>
    );

    expect(screen.getByText(/No textual differences detected/i)).toBeInTheDocument();
    expect(screen.queryByText('Text comparison unavailable')).not.toBeInTheDocument();
  });

  it('opens edit modal and delete modal from target detail page', async () => {
    mockTextQueries({
      'snap-baseline': { data: 'old' },
      'snap-latest': { data: 'new' },
    });

    render(
      <BrowserRouter>
        <TargetDetailPage />
      </BrowserRouter>
    );

    const editBtn = screen.getByTestId('detail-edit-target-btn');
    expect(editBtn).toBeInTheDocument();
    fireEvent.click(editBtn);
    expect(screen.getByRole('dialog', { name: /Edit Target Production Gateway/i })).toBeInTheDocument();

    const cancelEditBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelEditBtn);

    const deleteBtn = screen.getByTestId('detail-delete-target-btn');
    expect(deleteBtn).toBeInTheDocument();
    fireEvent.click(deleteBtn);
    expect(screen.getByRole('dialog', { name: /Delete Target Production Gateway/i })).toBeInTheDocument();
  });
});
