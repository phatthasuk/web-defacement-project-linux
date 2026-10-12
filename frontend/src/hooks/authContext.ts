import { createContext, useContext } from 'react';

export interface User {
  id: number;
  username: string;
  is_active: boolean;
  role: 'admin' | 'operator';
  display_name: string;
  registration_status: 'pending' | 'approved' | 'rejected';
  must_change_password: boolean;
}

export interface AuthResponse extends User {
  csrf_token: string;
}

export interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  authError: boolean;
  applyAuth: (auth: AuthResponse) => void;
  logout: () => Promise<void>;
  retry: () => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
