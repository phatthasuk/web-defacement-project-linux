import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiFetch } from '../api/client';
import { useAuth } from './authContext';
import { AuthProvider } from './useAuth';

vi.mock('../api/client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/client')>();
  return {
    ...original,
    apiFetch: vi.fn(),
    setCsrfToken: vi.fn(),
  };
});

const mockedApiFetch = vi.mocked(apiFetch);
const authenticatedUser = {
  id: 1,
  username: 'operator',
  is_active: true,
  role: 'admin',
  display_name: 'Operator',
  registration_status: 'approved',
  must_change_password: false,
  csrf_token: 'csrf-token',
};

function AuthProbe() {
  const { user, isLoading, authError, logout } = useAuth();
  if (isLoading) return <span>loading</span>;
  return (
    <div>
      <span>{user ? `user:${user.username}` : 'logged-out'}</span>
      {authError && <span>auth-error</span>}
      <button onClick={() => void logout().catch(() => undefined)}>logout</button>
    </div>
  );
}

function renderAuth() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>
    </QueryClientProvider>
  );
  return queryClient;
}

describe('AuthProvider logout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApiFetch.mockResolvedValueOnce(authenticatedUser);
  });

  it('clears authentication after the server confirms logout', async () => {
    mockedApiFetch.mockResolvedValueOnce({});
    renderAuth();
    await screen.findByText('user:operator');

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));

    await screen.findByText('logged-out');
  });

  it('treats a 401 response as an already-ended session', async () => {
    mockedApiFetch.mockRejectedValueOnce(new ApiError(401, 'Not authenticated'));
    renderAuth();
    await screen.findByText('user:operator');

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));

    await screen.findByText('logged-out');
  });

  it('preserves authentication on server and network errors', async () => {
    mockedApiFetch.mockRejectedValueOnce(new ApiError(500, 'Server unavailable'));
    renderAuth();
    await screen.findByText('user:operator');

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText('user:operator')).toBeInTheDocument();
  });

  it('can retry after a lost response and finish logging out', async () => {
    mockedApiFetch
      .mockRejectedValueOnce(new TypeError('Network error'))
      .mockResolvedValueOnce({});
    renderAuth();
    await screen.findByText('user:operator');

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText('user:operator')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));
    await screen.findByText('logged-out');
  });
});

describe('AuthProvider focus revalidation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApiFetch.mockResolvedValueOnce(authenticatedUser);
  });

  it('revalidates on focus without showing loading or unmounting the authenticated view', async () => {
    mockedApiFetch.mockResolvedValueOnce(authenticatedUser);
    renderAuth();
    await screen.findByText('user:operator');

    fireEvent.focus(window);

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText('user:operator')).toBeInTheDocument();
    expect(screen.queryByText('loading')).not.toBeInTheDocument();
  });

  it('clears the session when focus revalidation returns 401', async () => {
    mockedApiFetch.mockRejectedValueOnce(new ApiError(401, 'Not authenticated'));
    renderAuth();
    await screen.findByText('user:operator');

    fireEvent.focus(window);

    await screen.findByText('logged-out');
    expect(screen.queryByText('auth-error')).not.toBeInTheDocument();
  });

  it.each([
    ['server error', new ApiError(500, 'Server unavailable')],
    ['network error', new TypeError('Network error')],
  ])('keeps the authenticated view after a background %s', async (_label, error) => {
    mockedApiFetch.mockRejectedValueOnce(error);
    renderAuth();
    await screen.findByText('user:operator');

    fireEvent.focus(window);

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText('user:operator')).toBeInTheDocument();
    expect(screen.queryByText('auth-error')).not.toBeInTheDocument();
    expect(screen.queryByText('loading')).not.toBeInTheDocument();
  });

  it('throttles repeated focus and visibility events during the cooldown', async () => {
    mockedApiFetch.mockResolvedValueOnce(authenticatedUser);
    renderAuth();
    await screen.findByText('user:operator');

    fireEvent.focus(window);
    fireEvent.focus(window);
    fireEvent(document, new Event('visibilitychange'));

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText('user:operator')).toBeInTheDocument();
  });
});
