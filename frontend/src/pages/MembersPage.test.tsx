import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '../api/client';
import { MembersPage } from './MembersPage';

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>();
  return {
    ...original,
    apiFetch: vi.fn(),
  };
});

const mockedApiFetch = vi.mocked(apiFetch);

const activeOperator = {
  id: 10,
  username: 'alice',
  display_name: 'Alice Operator',
  role: 'operator',
  is_active: true,
  status: 'active',
  last_login_at: null,
  registration_at: '2026-10-19T00:00:00Z',
  assigned_website_count: 1,
  must_change_password: false,
};

const pendingOperator = {
  id: 11,
  username: 'bob',
  display_name: 'Bob Pending',
  role: 'operator',
  is_active: false,
  status: 'pending',
  last_login_at: null,
  registration_at: '2026-10-19T00:00:00Z',
  assigned_website_count: 0,
  must_change_password: false,
};

function renderMembersPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MembersPage />
    </QueryClientProvider>
  );
}

describe('MembersPage behavioral regressions (F-03 & F-09)', () => {
  let currentAlice = { ...activeOperator };

  beforeEach(() => {
    vi.clearAllMocks();
    currentAlice = { ...activeOperator };

    mockedApiFetch.mockImplementation(async (path: string, options?: RequestInit) => {
      const method = (options?.method || 'GET').toUpperCase();
      if (path.startsWith('/members?') && method === 'GET') {
        const params = new URLSearchParams(path.split('?')[1]);
        const statusFilter = params.get('status');
        const limit = params.get('limit');
        if (limit === '200') {
          return {
            items: [currentAlice, pendingOperator],
            pending_count: 1,
            total: 2,
          };
        }
        if (statusFilter === 'active') {
          return {
            items: [currentAlice],
            pending_count: 1,
            total: 1,
          };
        }
        if (statusFilter === 'pending') {
          return {
            items: [pendingOperator],
            pending_count: 1,
            total: 1,
          };
        }
        return {
          items: [currentAlice, pendingOperator],
          pending_count: 1,
          total: 2,
        };
      }
      if (path === '/members/10' && method === 'PATCH') {
        const body = JSON.parse(String(options?.body || '{}')) as { display_name?: string };
        currentAlice = {
          ...currentAlice,
          display_name: body.display_name || currentAlice.display_name,
        };
        return currentAlice;
      }
      if (path === '/members/10' && method === 'GET') {
        return currentAlice;
      }
      if (path.startsWith('/members/10/websites')) {
        return {
          items: [
            {
              id: 'site-1',
              name: 'Portal',
              url: 'https://portal.example.com',
              is_active: true,
              tags: [],
            },
          ],
        };
      }
      if (path.startsWith('/member-assignments/websites')) {
        return {
          items: [
            {
              id: 'site-1',
              name: 'Portal',
              url: 'https://portal.example.com',
              is_active: true,
              tags: [],
              assignees: [],
            },
          ],
          total: 1,
          counts: { all: 1, unassigned: 1, assigned: 0 },
        };
      }
      if (path.startsWith('/tags')) {
        return { items: [] };
      }
      return {};
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('preserves active status filter and refreshes selected member details after a mutation (F-03)', async () => {
    renderMembersPage();
    await screen.findByText('Alice Operator');
    expect(screen.getByText('Bob Pending')).toBeInTheDocument();

    // Filter by status = active
    const statusSelect = screen.getByDisplayValue('All statuses');
    fireEvent.change(statusSelect, { target: { value: 'active' } });

    await waitFor(() => {
      expect(screen.queryByText('Bob Pending')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Alice Operator')).toBeInTheDocument();

    // Select Alice and update display name
    fireEvent.click(screen.getByRole('button', { name: 'Alice Operator' }));
    await screen.findByText('Member details · Alice Operator');

    const nameInput = screen.getByLabelText('Display name');
    fireEvent.change(nameInput, { target: { value: 'Alice Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save name' }));

    // Selected member header and table row update, and pending Bob does NOT reappear from unfiltered loadAssignments
    await screen.findByText('Member details · Alice Renamed');
    expect(screen.getByRole('button', { name: 'Alice Renamed' })).toBeInTheDocument();
    expect(screen.queryByText('Bob Pending')).not.toBeInTheDocument();
  });

  it('does not submit rejection when Cancel is clicked on the rejection reason prompt (F-09)', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(window, 'prompt').mockReturnValue(null);

    renderMembersPage();
    await screen.findByText('Bob Pending');

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));

    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      '/members/11/reject',
      expect.anything()
    );
  });

  it('uses a masked password input instead of window.prompt when resetting an operator password (F-09)', async () => {
    const promptSpy = vi.spyOn(window, 'prompt');

    renderMembersPage();
    await screen.findByText('Alice Operator');

    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }));
    expect(promptSpy).not.toHaveBeenCalled();

    const passwordInput = screen.getByLabelText('Temporary password') as HTMLInputElement;
    expect(passwordInput.type).toBe('password');

    fireEvent.change(passwordInput, { target: { value: 'new-temp-pass-1234' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm reset' }));

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/members/10/reset-password',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ temporary_password: 'new-temp-pass-1234' }),
        })
      );
    });
  });
});
