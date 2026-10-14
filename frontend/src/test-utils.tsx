import type { ReactElement, ReactNode } from 'react';
import { render as rtlRender, type RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthContext, type User } from './hooks/authContext';

export const adminUser: User = {
  id: 1,
  username: 'admin',
  is_active: true,
  role: 'admin',
  display_name: 'Admin User',
  registration_status: 'approved',
  must_change_password: false,
};

export const operatorUser: User = {
  ...adminUser,
  id: 2,
  username: 'operator',
  role: 'operator',
  display_name: 'Operator User',
};

export function render(
  ui: ReactElement,
  { role = 'admin', ...options }: RenderOptions & { role?: User['role'] } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const user = role === 'admin' ? adminUser : operatorUser;
  return rtlRender(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={{
        user, isLoading: false, authError: false,
        applyAuth: () => undefined, logout: async () => undefined, retry: () => undefined,
      }}>
        {ui as ReactNode}
      </AuthContext.Provider>
    </QueryClientProvider>,
    options,
  );
}
