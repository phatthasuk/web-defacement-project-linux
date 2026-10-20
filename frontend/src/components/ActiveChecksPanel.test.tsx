import { act, fireEvent, screen } from '@testing-library/react';
import { useState } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/client';
import { render } from '../test-utils';
import { ActiveChecksPanel } from './ActiveChecksPanel';
import * as targetHooks from '../hooks/useTargets';
import type { CheckActivity } from '../types/target';

vi.mock('../hooks/useTargets', () => ({
  TARGETS_QUERY_KEY: ['targets'],
  CHECK_ACTIVITY_QUERY_KEY: ['target-check-activity'],
  useActivityTargetQuery: vi.fn(),
  useCheckActivityQuery: vi.fn(),
}));

const sampleActivity: CheckActivity = {
  items: [
    {
      id: 'target-1',
      name: 'First Monitor',
      status: 'Checking',
      url_revision: 1,
      check_run_id: 'run-1',
      check_run_source: 'manual',
      check_attempt_count: 1,
      check_retry_max_attempts: 3,
      next_check_at: null,
      last_error_code: null,
      progress: {
        run_id: 'run-1',
        url_revision: 1,
        attempt_number: 1,
        phase: 'capturing',
        state: 'running',
        attempt_started_at: '2026-10-20T00:00:00Z',
        phase_started_at: '2026-10-20T00:00:00Z',
        updated_at: '2026-10-20T00:00:00Z',
        finished_at: null,
        outcome: null,
        error_code: null,
        steps: [
          {
            phase: 'opening_page',
            state: 'completed',
            started_at: '2026-10-20T00:00:00Z',
            finished_at: '2026-10-20T00:00:01Z',
          },
          {
            phase: 'capturing',
            state: 'running',
            started_at: '2026-10-20T00:00:01Z',
            finished_at: null,
          },
        ],
      },
    },
    {
      id: 'target-2',
      name: 'Second Monitor',
      status: 'Failed',
      url_revision: 1,
      check_run_id: 'run-2',
      check_run_source: 'retry',
      check_attempt_count: 2,
      check_retry_max_attempts: 3,
      next_check_at: '2026-10-20T01:00:00Z',
      last_error_code: 'upstream_connection',
      progress: null,
    },
  ],
  total: 21,
  limit: 20,
  offset: 0,
  observed_at: '2026-10-20T00:00:05Z',
};

describe('ActiveChecksPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(targetHooks.useCheckActivityQuery).mockReturnValue({
      data: sampleActivity,
      isPending: false,
      isError: false,
      isRefetchError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof targetHooks.useCheckActivityQuery>);
    vi.mocked(targetHooks.useActivityTargetQuery).mockReturnValue({
      data: undefined,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof targetHooks.useActivityTargetQuery>);
  });

  it('starts collapsed and expands progress inside the selected card', () => {
    render(<BrowserRouter><ActiveChecksPanel wide /></BrowserRouter>);

    expect(screen.getByRole('complementary', { name: 'Active checks' })).toBeInTheDocument();
    expect(screen.getByText('All active monitors you can access')).toBeInTheDocument();
    expect(screen.getByText('Showing 1–2 of 21')).toBeInTheDocument();
    const firstCard = screen.getByRole('button', { name: /First Monitor/ });
    expect(firstCard).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region', { name: 'First Monitor' })).not.toBeInTheDocument();

    fireEvent.click(firstCard);

    expect(screen.getByRole('button', { name: /First Monitor/ })).toHaveAttribute('aria-expanded', 'true');
    const firstRegion = screen.getByRole('region', { name: 'First Monitor' });
    expect(firstCard.closest('li')).toContainElement(firstRegion);
    expect(screen.getAllByText('First Monitor')).toHaveLength(1);
    expect(screen.getByText('Done · Open website')).toBeInTheDocument();
    expect(screen.getByText('Running · Capture page data')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View First Monitor' })).toBeInTheDocument();
  });

  it('switches to one card at a time and keeps retry state visible', () => {
    render(<BrowserRouter><ActiveChecksPanel wide /></BrowserRouter>);
    fireEvent.click(screen.getByRole('button', { name: /First Monitor/ }));
    fireEvent.click(screen.getByRole('button', { name: /Second Monitor/ }));

    expect(screen.queryByRole('region', { name: 'First Monitor' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Second Monitor' })).toBeInTheDocument();
    expect(screen.getByText(/Retry scheduled/)).toBeInTheDocument();
    expect(screen.getByText(/Next attempt/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Second Monitor/ }));
    expect(screen.queryByRole('region', { name: 'Second Monitor' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Second Monitor/ })).toHaveAttribute('aria-expanded', 'false');
  });

  it('keeps a manually collapsed card closed after an activity refresh', () => {
    function RefreshHarness() {
      const [, setRefresh] = useState(0);
      return <>
        <button type="button" onClick={() => setRefresh((value) => value + 1)}>Refresh render</button>
        <BrowserRouter><ActiveChecksPanel wide /></BrowserRouter>
      </>;
    }
    render(<RefreshHarness />);
    fireEvent.click(screen.getByRole('button', { name: /First Monitor/ }));
    fireEvent.click(screen.getByRole('button', { name: /First Monitor/ }));

    vi.mocked(targetHooks.useCheckActivityQuery).mockReturnValue({
      data: { ...sampleActivity, items: [...sampleActivity.items] },
      isPending: false,
      isError: false,
      isRefetchError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof targetHooks.useCheckActivityQuery>);
    fireEvent.click(screen.getByRole('button', { name: 'Refresh render' }));

    expect(screen.getByRole('button', { name: /First Monitor/ })).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region', { name: 'First Monitor' })).not.toBeInTheDocument();
  });

  it('keeps a confirmed terminal card briefly, then removes it after the retention window', () => {
    vi.useFakeTimers();
    function RefreshHarness() {
      const [, setRefresh] = useState(0);
      return <>
        <button type="button" onClick={() => setRefresh((value) => value + 1)}>Refresh render</button>
        <BrowserRouter><ActiveChecksPanel wide /></BrowserRouter>
      </>;
    }
    try {
      render(<RefreshHarness />);
      fireEvent.click(screen.getByRole('button', { name: /First Monitor/ }));
      const finished = {
        ...sampleActivity.items[0].progress!,
        state: 'finished' as const,
        phase: 'saving_result',
        outcome: 'OK',
        finished_at: '2026-10-20T00:01:00Z',
      };
      vi.mocked(targetHooks.useCheckActivityQuery).mockReturnValue({
        data: { ...sampleActivity, items: [sampleActivity.items[1]], total: 1 },
        isPending: false,
        isError: false,
        isRefetchError: false,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof targetHooks.useCheckActivityQuery>);
      vi.mocked(targetHooks.useActivityTargetQuery).mockReturnValue({
        data: {
          id: 'target-1',
          name: 'First Monitor',
          status: 'OK',
          url_revision: 1,
          check_run_id: null,
          check_attempt_count: 1,
          check_retry_max_attempts: 3,
          check_progress: finished,
        },
        isError: false,
        isFetching: false,
        error: null,
        errorUpdatedAt: 0,
      } as unknown as ReturnType<typeof targetHooks.useActivityTargetQuery>);
      fireEvent.click(screen.getByRole('button', { name: 'Refresh render' }));

      expect(screen.getByText('Completed recently')).toBeInTheDocument();
      expect(screen.getByRole('region', { name: 'First Monitor' })).toBeInTheDocument();

      act(() => vi.advanceTimersByTime(60_000));

      expect(screen.queryByRole('region', { name: 'First Monitor' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /First Monitor/ })).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('clears a retained card immediately when its selected-target response is 404', () => {
    function RefreshHarness() {
      const [, setRefresh] = useState(0);
      return <>
        <button type="button" onClick={() => setRefresh((value) => value + 1)}>Refresh render</button>
        <BrowserRouter><ActiveChecksPanel wide /></BrowserRouter>
      </>;
    }
    render(<RefreshHarness />);
    fireEvent.click(screen.getByRole('button', { name: /First Monitor/ }));
    vi.mocked(targetHooks.useCheckActivityQuery).mockReturnValue({
      data: { ...sampleActivity, items: [sampleActivity.items[1]], total: 1 },
      isPending: false,
      isError: false,
      isRefetchError: false,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof targetHooks.useCheckActivityQuery>);
    vi.mocked(targetHooks.useActivityTargetQuery).mockReturnValue({
      data: undefined,
      isError: true,
      isFetching: false,
      error: new ApiError(404, 'Not found'),
      errorUpdatedAt: Date.now(),
    } as unknown as ReturnType<typeof targetHooks.useActivityTargetQuery>);

    fireEvent.click(screen.getByRole('button', { name: 'Refresh render' }));

    expect(screen.queryByRole('button', { name: /First Monitor/ })).not.toBeInTheDocument();
    expect(screen.getByText('The selected monitor is no longer available.')).toBeInTheDocument();
  });

  it('distinguishes refresh failure from a successful empty response', () => {
    vi.mocked(targetHooks.useCheckActivityQuery).mockReturnValue({
      data: { ...sampleActivity, items: [], total: 0 },
      isPending: false,
      isError: false,
      isRefetchError: true,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof targetHooks.useCheckActivityQuery>);
    render(<BrowserRouter><ActiveChecksPanel wide /></BrowserRouter>);

    expect(screen.getByText('No active checks')).toBeInTheDocument();
    expect(screen.getByText(/Refresh failed/)).toBeInTheDocument();
  });
});
