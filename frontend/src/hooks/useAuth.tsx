import { useState, useEffect, useCallback, useRef, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError, setCsrfToken } from '../api/client';
import { AuthContext, type AuthResponse, type User } from './authContext';

const FOCUS_REVALIDATE_COOLDOWN_MS = 15_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const queryClient = useQueryClient();
  const userRef = useRef<User | null>(null);
  const lastCheckedAtRef = useRef<number | null>(null);
  const checkInFlightRef = useRef(false);

  const updateUser = useCallback((nextUser: User | null) => {
    userRef.current = nextUser;
    setUser(nextUser);
  }, []);

  const applyAuth = useCallback(({ csrf_token, ...currentUser }: AuthResponse) => {
    setCsrfToken(csrf_token);
    if (userRef.current && userRef.current.id !== currentUser.id) queryClient.clear();
    updateUser(currentUser);
    setAuthError(false);
  }, [queryClient, updateUser]);

  const checkAuth = useCallback(async (showLoading: boolean) => {
    if (showLoading) setIsLoading(true);
    if (checkInFlightRef.current) return;
    checkInFlightRef.current = true;

    try {
      const auth = await apiFetch<AuthResponse>('/auth/me');
      applyAuth(auth);
      lastCheckedAtRef.current = Date.now();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        updateUser(null);
        setCsrfToken(null);
        setAuthError(false);
        queryClient.clear();
      } else if (!userRef.current) {
        // Initial load and explicit retry need an error screen when no session
        // is available. A transient background failure keeps the current page.
        setAuthError(true);
      }
    } finally {
      checkInFlightRef.current = false;
      setIsLoading(false);
    }
  }, [applyAuth, queryClient, updateUser]);

  useEffect(() => {
    void checkAuth(true);
  }, [checkAuth, reloadKey]);

  useEffect(() => {
    const onFocus = () => {
      const lastCheckedAt = lastCheckedAtRef.current;
      if (
        lastCheckedAt !== null &&
        Date.now() - lastCheckedAt < FOCUS_REVALIDATE_COOLDOWN_MS
      ) {
        return;
      }

      void checkAuth(false);
      void queryClient.invalidateQueries();
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') onFocus();
    };
    const onAccessDenied = (event: Event) => {
      const status = (event as CustomEvent<{ status: number }>).detail?.status;
      if (status === 401) {
        updateUser(null);
        setCsrfToken(null);
        setAuthError(false);
        queryClient.clear();
      } else {
        queryClient.clear();
      }
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('api:access-denied', onAccessDenied);
    return () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('api:access-denied', onAccessDenied);
    };
  }, [checkAuth, queryClient, updateUser]);

  const logout = useCallback(async () => {
    try {
      await apiFetch('/auth/logout', { method: 'POST' });
      setCsrfToken(null);
      updateUser(null);
      setAuthError(false);
      queryClient.clear();
    } catch (e) {
      console.error('Logout failed:', e);
      if (e instanceof ApiError && e.status === 401) {
        setCsrfToken(null);
        updateUser(null);
        setAuthError(false);
        queryClient.clear();
        return;
      }
      throw e;
    }
  }, [queryClient, updateUser]);

  const retry = useCallback(() => setReloadKey((key) => key + 1), []);

  return (
    <AuthContext.Provider value={{ user, isLoading, authError, applyAuth, logout, retry }}>
      {children}
    </AuthContext.Provider>
  );
}
