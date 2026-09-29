import { useState, useEffect, useCallback, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError, setCsrfToken } from '../api/client';
import { AuthContext, type AuthResponse, type User } from './authContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const queryClient = useQueryClient();

  const applyAuth = useCallback(({ csrf_token, ...currentUser }: AuthResponse) => {
    setCsrfToken(csrf_token);
    setUser(currentUser);
    setAuthError(false);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      setIsLoading(true);
      try {
        const auth = await apiFetch<AuthResponse>('/auth/me');
        if (cancelled) return;
        applyAuth(auth);
      } catch (error) {
        if (cancelled) return;
        setUser(null);
        setCsrfToken(null);
        // 401 = not authenticated (expected). Anything else (network / 5xx) is a
        // service error the user should be told about, not treated as logged out.
        setAuthError(!(error instanceof ApiError && error.status === 401));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    checkAuth();
    return () => {
      cancelled = true;
    };
  }, [applyAuth, reloadKey]);

  const logout = useCallback(async () => {
    try {
      await apiFetch('/auth/logout', { method: 'POST' });
      setCsrfToken(null);
      setUser(null);
      setAuthError(false);
      queryClient.clear();
    } catch (e) {
      console.error('Logout failed:', e);
      if (e instanceof ApiError && e.status === 401) {
        setCsrfToken(null);
        setUser(null);
        setAuthError(false);
        queryClient.clear();
        return;
      }
      throw e;
    }
  }, [queryClient]);

  const retry = useCallback(() => setReloadKey((key) => key + 1), []);

  return (
    <AuthContext.Provider value={{ user, isLoading, authError, applyAuth, logout, retry }}>
      {children}
    </AuthContext.Provider>
  );
}
