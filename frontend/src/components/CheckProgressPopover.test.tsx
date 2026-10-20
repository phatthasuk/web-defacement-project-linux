import { act, fireEvent, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CheckProgressPopover } from './CheckProgressPopover';
import type { Target } from '../types/target';
import { render } from '../test-utils';

const target = {
  id: 'target-1',
  name: 'Example',
  url: 'https://example.test',
  url_revision: 1,
  status: 'Checking',
  is_active: true,
  last_error: null,
  created_at: '2026-10-20T00:00:00Z',
  updated_at: '2026-10-20T00:00:00Z',
  check_run_id: 'run-1',
  check_retry_max_attempts: 3,
  check_progress: {
    run_id: 'run-1',
    url_revision: 1,
    attempt_number: 1,
    phase: 'comparing',
    state: 'running',
    attempt_started_at: new Date().toISOString(),
    phase_started_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    finished_at: null,
    outcome: null,
    error_code: null,
    steps: [{ phase: 'opening_page', state: 'completed', started_at: new Date().toISOString(), finished_at: new Date().toISOString() }],
  },
} as Target;

describe('CheckProgressPopover', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('opens on keyboard focus and shows backend progress', () => {
    render(<CheckProgressPopover target={target}><span>Checking</span></CheckProgressPopover>);
    fireEvent.focus(screen.getByRole('button', { name: 'View check progress' }));
    expect(screen.getByRole('region', { name: 'Check progress' })).toBeInTheDocument();
    expect(screen.getByText('Compare with baselines')).toBeInTheDocument();
    expect(screen.getByText(/Done · Open website/)).toBeInTheDocument();
  });

  it('opens after the pointer hover delay and closes on Escape', async () => {
    vi.useFakeTimers();
    render(<CheckProgressPopover target={target}><span>Checking</span></CheckProgressPopover>);
    const trigger = screen.getByRole('button', { name: 'View check progress' });
    fireEvent.mouseEnter(trigger);
    act(() => vi.advanceTimersByTime(300));
    expect(screen.getByRole('region', { name: 'Check progress' })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('region', { name: 'Check progress' })).not.toBeInTheDocument();
  });

  it('cancels a pending hover open when the pointer leaves early', () => {
    vi.useFakeTimers();
    render(<CheckProgressPopover target={target}><span>Checking</span></CheckProgressPopover>);
    const trigger = screen.getByRole('button', { name: 'View check progress' });
    fireEvent.mouseEnter(trigger);
    act(() => vi.advanceTimersByTime(100));
    fireEvent.mouseLeave(trigger);
    act(() => vi.advanceTimersByTime(500));
    expect(screen.queryByRole('region', { name: 'Check progress' })).not.toBeInTheDocument();
  });

  it('closes on Escape from the close button and restores focus without reopening', () => {
    render(<CheckProgressPopover target={target}><span>Checking</span></CheckProgressPopover>);
    const trigger = screen.getByRole('button', { name: 'View check progress' });
    fireEvent.focus(trigger);
    const close = screen.getByRole('button', { name: 'Close progress' });
    close.focus();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('region', { name: 'Check progress' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('does not steal focus when Escape dismisses a hover-opened panel', () => {
    vi.useFakeTimers();
    render(<CheckProgressPopover target={target}><span>Checking</span></CheckProgressPopover>);
    const trigger = screen.getByRole('button', { name: 'View check progress' });
    const outside = document.createElement('button');
    document.body.append(outside);
    fireEvent.mouseEnter(trigger);
    act(() => vi.advanceTimersByTime(300));
    outside.focus();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('region', { name: 'Check progress' })).not.toBeInTheDocument();
    expect(outside).toHaveFocus();
    outside.remove();
  });

  it('opens after a later intentional keyboard focus following Escape', () => {
    render(<CheckProgressPopover target={target}><span>Checking</span></CheckProgressPopover>);
    const trigger = screen.getByRole('button', { name: 'View check progress' });
    fireEvent.focus(trigger);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('region', { name: 'Check progress' })).not.toBeInTheDocument();
    fireEvent.blur(trigger);
    fireEvent.focus(trigger);
    expect(screen.getByRole('region', { name: 'Check progress' })).toBeInTheDocument();
  });
});
