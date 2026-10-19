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
  const authEpochRef = useRef(0);

  const updateUser = useCallback((nextUser: User | null) => {
    userRef.current = nextUser;
    setUser(nextUser);
  }, []);

  const clearSession = useCallback(() => {
    authEpochRef.current += 1;
    checkInFlightRef.current = false;
    setCsrfToken(null);
    updateUser(null);
    setAuthError(false);
    queryClient.clear();
  }, [queryClient, updateUser]);

  const applyAuth = useCallback(({ csrf_token, ...currentUser }: AuthResponse) => {
    authEpochRef.current += 1;
    checkInFlightRef.current = false;
    setCsrfToken(csrf_token);
    const prev = userRef.current;
    if (
      prev &&
      (prev.id !== currentUser.id ||
        prev.role !== currentUser.role ||
        prev.must_change_password !== currentUser.must_change_password)
    ) {
      queryClient.clear();
    }
    updateUser(currentUser);
    setAuthError(false);
    lastCheckedAtRef.current = Date.now();
  }, [queryClient, updateUser]);

  const checkAuth = useCallback(async (showLoading: boolean) => {
    if (showLoading) setIsLoading(true);
    if (checkInFlightRef.current) return;
    checkInFlightRef.current = true;
    const requestEpoch = ++authEpochRef.current;

    try {
      const auth = await apiFetch<AuthResponse>('/auth/me');
      if (requestEpoch !== authEpochRef.current) return;
      applyAuth(auth);
    } catch (error) {
      if (requestEpoch !== authEpochRef.current) return;
      if (error instanceof ApiError && error.status === 401) {
        clearSession();
      } else if (!userRef.current) {
        // Initial load and explicit retry need an error screen when no session
        // is available. A transient background failure keeps the current page.
        setAuthError(true);
      }
    } finally {
      if (requestEpoch === authEpochRef.current) {
        checkInFlightRef.current = false;
      }
      setIsLoading(false);
    }
  }, [applyAuth, clearSession]);

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
      if (checkInFlightRef.current) {
        return;
      }

      lastCheckedAtRef.current = Date.now();
      void checkAuth(false);
      void queryClient.invalidateQueries();
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') onFocus();
    };
    const onAccessDenied = (event: Event) => {
      const status = (event as CustomEvent<{ status: number }>).detail?.status;
      if (status === 401) {
        clearSession();
      } else if (status === 403) {
        void checkAuth(false);
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
  }, [checkAuth, clearSession, queryClient]);

  const logout = useCallback(async () => {
    try {
      await apiFetch('/auth/logout', { method: 'POST' });
      clearSession();
    } catch (e) {
      console.error('Logout failed:', e);
      if (e instanceof ApiError && e.status === 401) {
        clearSession();
        return;
      }
      throw e;
    }
  }, [clearSession]);

  const retry = useCallback(() => setReloadKey((key) => key + 1), []);

  return (
    <AuthContext.Provider value={{ user, isLoading, authError, applyAuth, logout, retry }}>
      {children}
    </AuthContext.Provider>
  );
}
