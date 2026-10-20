import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '../test-utils';
import { CheckProgressDetails } from './CheckProgressDetails';
import type { CheckProgress } from '../types/target';

const progress: CheckProgress = {
  run_id: 'run-1',
  url_revision: 4,
  attempt_number: 2,
  phase: 'waiting_page_ready',
  state: 'retry_wait',
  attempt_started_at: '2026-10-20T00:00:00Z',
  phase_started_at: '2026-10-20T00:01:00Z',
  updated_at: '2026-10-20T00:01:00Z',
  finished_at: null,
  outcome: null,
  error_code: null,
  steps: [
    { phase: 'opening_page', state: 'completed', started_at: '2026-10-20T00:00:00Z', finished_at: '2026-10-20T00:00:10Z' },
    { phase: 'waiting_page_ready', state: 'retry_wait', started_at: '2026-10-20T00:00:10Z', finished_at: null },
    { phase: 'capturing', state: 'skipped', started_at: '2026-10-20T00:00:10Z', finished_at: null },
  ],
};

describe('CheckProgressDetails', () => {
  it('preserves retry attempt, skipped steps, and the next retry deadline', () => {
    render(<CheckProgressDetails progress={progress} status="Failed" nextCheckAt="2026-10-20T00:05:00Z" elapsed={12} />);

    expect(screen.getByText('Elapsed 12s · Attempt 2')).toBeInTheDocument();
    expect(screen.getByText('Waiting · Wait for page readiness')).toBeInTheDocument();
    expect(screen.getByText('Skipped · Capture page data')).toBeInTheDocument();
    expect(screen.getByText(/Next attempt/)).toBeInTheDocument();
  });

  it('keeps unavailable progress, loading, refresh failure, and finalization diagnostics distinct', () => {
    const { rerender } = render(<CheckProgressDetails progress={null} status="Checking" elapsed={0} loading />);
    expect(screen.getByText('Loading check progress…')).toBeInTheDocument();
    expect(screen.queryByText('Progress details unavailable')).not.toBeInTheDocument();

    rerender(<CheckProgressDetails progress={null} status="Checking" elapsed={0} refreshFailed />);
    expect(screen.getByText('Progress details unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Unable to refresh progress/)).toBeInTheDocument();

    rerender(<CheckProgressDetails progress={{ ...progress, state: 'finished', outcome: 'OK', error_code: 'attempt_finalization_unconfirmed' }} status="OK" elapsed={0} />);
    expect(screen.getByText('Finished · OK')).toBeInTheDocument();
    expect(screen.getByText(/attempt finalization could not be confirmed/)).toBeInTheDocument();
  });
});
