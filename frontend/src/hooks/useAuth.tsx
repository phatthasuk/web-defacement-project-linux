import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiFetch, ApiError, setCsrfToken } from '../api/client';

export interface User {
  id: number;
  username: string;
  is_active: boolean;
  role: string;
}

interface AuthResponse extends User {
  csrf_token: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  // Set when /auth/me fails for a reason other than "not logged in" (network
  // error or HTTP 5xx). Distinguishing this from an expired session avoids a
  // misleading redirect-to-login loop.
  authError: boolean;
  applyAuth: (auth: AuthResponse) => void;
  logout: () => Promise<void>;
  retry: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

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
    } catch (e) {
      console.error(e);
    }
    setCsrfToken(null);
    setUser(null);
    setAuthError(false);
    queryClient.clear();
  }, [queryClient]);

  const retry = useCallback(() => setReloadKey((key) => key + 1), []);

  return (
    <AuthContext.Provider value={{ user, isLoading, authError, applyAuth, logout, retry }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
