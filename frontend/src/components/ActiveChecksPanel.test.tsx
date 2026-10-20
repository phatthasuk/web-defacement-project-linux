import { fireEvent, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '../test-utils';
import { ActiveChecksPanel } from './ActiveChecksPanel';
import * as targetHooks from '../hooks/useTargets';
import type { CheckActivity } from '../types/target';

vi.mock('../hooks/useTargets', () => ({
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

  it('shows accessible active monitors and the selected checklist', () => {
    render(<BrowserRouter><ActiveChecksPanel wide /></BrowserRouter>);

    expect(screen.getByRole('complementary', { name: 'Active checks' })).toBeInTheDocument();
    expect(screen.getByText('All active monitors you can access')).toBeInTheDocument();
    expect(screen.getByText('Showing 1–2 of 21')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'First Monitor' })).toBeInTheDocument();
    expect(screen.getByText('Done · Open website')).toBeInTheDocument();
    expect(screen.getByText('Running · Capture page data')).toBeInTheDocument();
  });

  it('selects a different active monitor and keeps retry state visible', () => {
    render(<BrowserRouter><ActiveChecksPanel wide /></BrowserRouter>);
    fireEvent.click(screen.getByRole('button', { name: /Second Monitor/ }));

    expect(screen.getByRole('heading', { name: 'Second Monitor' })).toBeInTheDocument();
    expect(screen.getByText(/Retry scheduled/)).toBeInTheDocument();
    expect(screen.getByText(/Next attempt/)).toBeInTheDocument();
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
