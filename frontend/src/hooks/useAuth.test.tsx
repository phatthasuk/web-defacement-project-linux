import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
  let currentTime = 1_000_000;

  beforeEach(() => {
    vi.clearAllMocks();
    currentTime = 1_000_000;
    vi.spyOn(Date, 'now').mockImplementation(() => currentTime);
    mockedApiFetch.mockResolvedValueOnce(authenticatedUser);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('revalidates on focus after cooldown without showing loading or unmounting the authenticated view', async () => {
    mockedApiFetch.mockResolvedValueOnce(authenticatedUser);
    renderAuth();
    await screen.findByText('user:operator');

    currentTime += 16_000;
    fireEvent.focus(window);

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText('user:operator')).toBeInTheDocument();
    expect(screen.queryByText('loading')).not.toBeInTheDocument();
  });

  it('clears the session when focus revalidation returns 401', async () => {
    mockedApiFetch.mockRejectedValueOnce(new ApiError(401, 'Not authenticated'));
    renderAuth();
    await screen.findByText('user:operator');

    currentTime += 16_000;
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

    currentTime += 16_000;
    fireEvent.focus(window);

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(screen.getByText('user:operator')).toBeInTheDocument();
    expect(screen.queryByText('auth-error')).not.toBeInTheDocument();
    expect(screen.queryByText('loading')).not.toBeInTheDocument();
  });

  it('throttles repeated focus and visibility events during the cooldown', async () => {
    renderAuth();
    await screen.findByText('user:operator');

    currentTime += 5_000;
    fireEvent.focus(window);
    fireEvent.focus(window);
    fireEvent(document, new Event('visibilitychange'));

    expect(mockedApiFetch).toHaveBeenCalledTimes(1);
    expect(screen.getByText('user:operator')).toBeInTheDocument();
  });

  it('does not double-fire or double-invalidate on paired visibilitychange and focus events after cooldown', async () => {
    mockedApiFetch.mockResolvedValueOnce(authenticatedUser);
    const queryClient = renderAuth();
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    await screen.findByText('user:operator');

    currentTime += 16_000;
    Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    fireEvent(document, new Event('visibilitychange'));
    fireEvent.focus(window);

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByText('user:operator')).toBeInTheDocument();
  });

  it('clears cached queries when role or must_change_password changes on revalidation', async () => {
    mockedApiFetch.mockResolvedValueOnce({
      ...authenticatedUser,
      role: 'operator',
    });
    const queryClient = renderAuth();
    await screen.findByText('user:operator');
    queryClient.setQueryData(['targets'], [{ id: 'target-1' }]);

    currentTime += 16_000;
    fireEvent.focus(window);

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(queryClient.getQueryData(['targets'])).toBeUndefined();

    queryClient.setQueryData(['targets'], [{ id: 'target-2' }]);
    mockedApiFetch.mockResolvedValueOnce({
      ...authenticatedUser,
      role: 'operator',
      must_change_password: true,
    });

    currentTime += 16_000;
    fireEvent.focus(window);

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(3));
    expect(queryClient.getQueryData(['targets'])).toBeUndefined();
  });

  it('preserves cached queries on 403/404 access-denied events and clears session/cache on 401', async () => {
    mockedApiFetch.mockResolvedValueOnce(authenticatedUser);
    const queryClient = renderAuth();
    await screen.findByText('user:operator');
    queryClient.setQueryData(['targets'], [{ id: 'cached-target' }]);

    window.dispatchEvent(new CustomEvent('api:access-denied', { detail: { status: 404 } }));
    expect(queryClient.getQueryData(['targets'])).toEqual([{ id: 'cached-target' }]);
    expect(screen.getByText('user:operator')).toBeInTheDocument();

    window.dispatchEvent(new CustomEvent('api:access-denied', { detail: { status: 403 } }));
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));
    expect(queryClient.getQueryData(['targets'])).toEqual([{ id: 'cached-target' }]);
    expect(screen.getByText('user:operator')).toBeInTheDocument();

    window.dispatchEvent(new CustomEvent('api:access-denied', { detail: { status: 401 } }));
    await screen.findByText('logged-out');
    expect(queryClient.getQueryData(['targets'])).toBeUndefined();
  });

  it('ignores a stale in-flight focus revalidation response that resolves after logout', async () => {
    let resolveBackgroundMe!: (value: typeof authenticatedUser) => void;
    mockedApiFetch
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveBackgroundMe = resolve;
          })
      )
      .mockResolvedValueOnce({});

    renderAuth();
    await screen.findByText('user:operator');

    currentTime += 16_000;
    fireEvent.focus(window);
    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByRole('button', { name: 'logout' }));
    await screen.findByText('logged-out');

    resolveBackgroundMe(authenticatedUser);
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(screen.getByText('logged-out')).toBeInTheDocument();
  });
});
