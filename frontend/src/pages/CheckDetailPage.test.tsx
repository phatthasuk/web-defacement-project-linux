import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { useQuery } from '@tanstack/react-query';
import { CheckDetailPage } from './CheckDetailPage';
import * as useTargetDetailHooks from '../hooks/useTargetDetail';

// Mock useParams to return mock id
vi.mock('react-router-dom', async (importOriginal) => {
  const original = await importOriginal<Record<string, unknown>>();
  return {
    ...original,
    useParams: () => ({ id: 'check-1' }),
  };
});

// Mock hooks
vi.mock('../hooks/useTargetDetail', () => ({
  useCheckQuery: vi.fn(),
  useTargetQuery: vi.fn(),
  useConfigQuery: vi.fn(),
}));

// Mock react-query useQuery for text diff fetching
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const original = await importOriginal<Record<string, unknown>>();
  return {
    ...original,
    useQuery: vi.fn().mockReturnValue({ data: 'Mock Snapshot Text Content', isLoading: false }),
  };
});

describe('CheckDetailPage', () => {
  const mockCheck = {
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
  };

  const mockTarget = {
    id: 'target-1',
    name: 'Production Gateway',
    url: 'https://example.com',
    status: 'Changed',
  };

  const useQueryMock = useQuery as unknown as Mock;

  interface TextQueryState {
    data?: string;
    isLoading?: boolean;
    isError?: boolean;
    isFetching?: boolean;
    refetch?: () => void;
  }

  /**
   * Drive each snapshot-text query independently, keyed by the snapshot id in
   * its queryKey, so one side can fail while the other succeeds.
   */
  const mockTextQueries = (states: Record<string, TextQueryState>) => {
    useQueryMock.mockImplementation((options: { queryKey?: unknown[]; enabled?: boolean }) => {
      const snapshotId = options.queryKey?.[1] as string | undefined;
      const base: TextQueryState = {
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

  const renderPage = () =>
    render(
      <BrowserRouter>
        <CheckDetailPage />
      </BrowserRouter>
    );

  beforeEach(() => {
    vi.clearAllMocks();

    // Re-establish the default (both artifacts load fine); individual tests
    // override this with mockTextQueries.
    useQueryMock.mockReturnValue({
      data: 'Mock Snapshot Text Content',
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    });

    vi.mocked(useTargetDetailHooks.useCheckQuery).mockReturnValue({
      data: mockCheck,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useCheckQuery>);

    vi.mocked(useTargetDetailHooks.useTargetQuery).mockReturnValue({
      data: mockTarget,
      isLoading: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useTargetQuery>);

    vi.mocked(useTargetDetailHooks.useConfigQuery).mockReturnValue({
      data: { text_change_threshold: 0.02, visual_change_threshold: 0.01, structure_change_threshold: 0.0 },
      isLoading: false,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useConfigQuery>);
  });

  it('renders check metadata, comparison scores, and target link', () => {
    render(
      <BrowserRouter>
        <CheckDetailPage />
      </BrowserRouter>
    );

    expect(screen.getByText('Check Details')).toBeInTheDocument();
    expect(screen.getByText('Production Gateway')).toBeInTheDocument();
    expect(screen.getByText('5.0%')).toBeInTheDocument(); // text score
    expect(screen.getByText('2.0%')).toBeInTheDocument(); // visual score
    expect(screen.getByText('Text content changed slightly.')).toBeInTheDocument();
    expect(screen.getByText('check-1')).toBeInTheDocument();
    expect(screen.getByText('snap-baseline')).toBeInTheDocument();
    expect(screen.getByText('snap-latest')).toBeInTheDocument();

    // Check back link to target
    const backLink = screen.getByText(/Back to Production Gateway/i).closest('a');
    expect(backLink).toHaveAttribute('href', '/targets/target-1');
  });

  it('renders loading state when check or target is loading', () => {
    vi.mocked(useTargetDetailHooks.useCheckQuery).mockReturnValue({
      isLoading: true,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useCheckQuery>);

    render(
      <BrowserRouter>
        <CheckDetailPage />
      </BrowserRouter>
    );

    expect(screen.getByText('Loading check details...')).toBeInTheDocument();
  });

  it('renders error state when check fails to load', () => {
    vi.mocked(useTargetDetailHooks.useCheckQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useTargetDetailHooks.useCheckQuery>);

    render(
      <BrowserRouter>
        <CheckDetailPage />
      </BrowserRouter>
    );

    expect(screen.getByText('Check Result Not Found')).toBeInTheDocument();
  });

  // --- Artifact retrieval failures must never read as "unchanged" (Finding 4) ---

  it('reports an error, not "no differences", when baseline text fails to load', () => {
    mockTextQueries({
      'snap-baseline': { isError: true },
      'snap-latest': { data: 'current content' },
    });

    renderPage();

    expect(screen.getByText('Text comparison unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Failed to load baseline text/i)).toBeInTheDocument();
    expect(screen.queryByText(/No textual differences detected/i)).not.toBeInTheDocument();
  });

  it('reports an error when current text fails to load', () => {
    mockTextQueries({
      'snap-baseline': { data: 'baseline content' },
      'snap-latest': { isError: true },
    });

    renderPage();

    expect(screen.getByText(/Failed to load current text/i)).toBeInTheDocument();
    expect(screen.queryByText(/No textual differences detected/i)).not.toBeInTheDocument();
  });

  it('reports both artifacts when each text request fails', () => {
    mockTextQueries({
      'snap-baseline': { isError: true },
      'snap-latest': { isError: true },
    });

    renderPage();

    expect(screen.getByText(/Failed to load baseline text and current text/i)).toBeInTheDocument();
    expect(screen.queryByText(/No textual differences detected/i)).not.toBeInTheDocument();
  });

  it('distinguishes successfully-empty artifacts from a failed request', () => {
    mockTextQueries({
      'snap-baseline': { data: '' },
      'snap-latest': { data: '' },
    });

    renderPage();

    // Both genuinely loaded and are empty — reporting "no differences" is correct here.
    expect(screen.getByText(/No textual differences detected/i)).toBeInTheDocument();
    expect(screen.queryByText('Text comparison unavailable')).not.toBeInTheDocument();
  });

  it('refetches only the failed text query when Retry is clicked', () => {
    const baselineRefetch = vi.fn();
    const currentRefetch = vi.fn();
    mockTextQueries({
      'snap-baseline': { isError: true, refetch: baselineRefetch },
      'snap-latest': { data: 'current content', refetch: currentRefetch },
    });

    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /Retry/i }));

    expect(baselineRefetch).toHaveBeenCalledTimes(1);
    expect(currentRefetch).not.toHaveBeenCalled();
  });

  it('shows a neutral notice when text artifacts were never requested', () => {
    mockTextQueries({});

    renderPage();

    expect(screen.getByText(/Text artifacts are not available for this check/i)).toBeInTheDocument();
    expect(screen.queryByText(/No textual differences detected/i)).not.toBeInTheDocument();
  });
});
