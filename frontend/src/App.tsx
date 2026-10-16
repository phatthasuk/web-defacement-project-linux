import { useEffect, useRef, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TargetListPage } from './pages/TargetListPage';
import { TargetDetailPage } from './pages/TargetDetailPage';
import { CheckDetailPage } from './pages/CheckDetailPage';
import { LoginPage } from './pages/LoginPage';
import { TagsPage } from './pages/TagsPage';
import { RegisterPage } from './pages/RegisterPage';
import { ChangePasswordPage } from './pages/ChangePasswordPage';
import { MembersPage } from './pages/MembersPage';
import { useAuth } from './hooks/authContext';
import { AuthProvider } from './hooks/useAuth';
import { LogOut, Menu, Tags, Users, X } from 'lucide-react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function ProtectedRoute({ children, adminOnly = false, allowPasswordChange = false }: { children: React.ReactNode; adminOnly?: boolean; allowPasswordChange?: boolean }) {
  const { user, isLoading, authError, retry } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (authError) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-950 gap-4 p-4 text-center">
        <p className="text-slate-300">
          Unable to reach the service. Please check your connection and try again.
        </p>
        <button
          onClick={retry}
          className="bg-blue-600 hover:bg-blue-500 text-white font-medium py-2 px-4 rounded-lg transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (user.must_change_password && !allowPasswordChange) return <Navigate to="/change-password" replace />;
  if (adminOnly && user.role !== 'admin') return <Navigate to="/" replace />;

  return <>{children}</>;
}

function NavBar() {
  const { user, logout } = useAuth();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isMenuOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !menuRef.current?.contains(event.target)) {
        setIsMenuOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsMenuOpen(false);
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isMenuOpen]);

  if (!user) return null;

  const handleLogout = async () => {
    try {
      setIsLoggingOut(true);
      setLogoutError(null);
      await logout();
    } catch {
      setLogoutError('Logout failed. Please try again.');
    } finally {
      setIsLoggingOut(false);
    }
  };

  return (
    <nav className="bg-slate-900 border-b border-slate-800 px-4 sm:px-6 py-3 flex justify-between items-center sticky top-0 z-10">
      <div className="font-bold text-lg text-slate-100 tracking-tight">
        Web Defacement Monitor
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-300">
          Welcome, <span className="font-medium text-slate-100">{user.display_name || user.username}</span>
        </span>
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setIsMenuOpen((open) => !open)}
            aria-expanded={isMenuOpen}
            aria-controls="account-menu"
            aria-label={`Open menu for ${user.display_name || user.username}`}
            className="flex items-center justify-center rounded-lg border border-slate-700 bg-slate-800 p-2 text-slate-300 transition-colors hover:border-slate-600 hover:bg-slate-700 hover:text-white focus:outline-none focus:ring-2 focus:ring-cyan-500"
          >
            {isMenuOpen ? <X className="h-4 w-4" aria-hidden="true" /> : <Menu className="h-4 w-4" aria-hidden="true" />}
          </button>

          {isMenuOpen && <div id="account-menu" className="absolute right-0 top-full z-20 mt-2 w-56 rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-xl shadow-black/30">
            <div className="flex flex-col gap-1">
              <NavLink
                to="/"
                end
                onClick={() => setIsMenuOpen(false)}
                className={({ isActive }) => `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${isActive ? 'bg-slate-800 text-cyan-300' : 'text-slate-300 hover:bg-slate-800 hover:text-white'}`}
              >
                Websites
              </NavLink>
              {user.role === 'admin' && <NavLink
                to="/tags"
                onClick={() => setIsMenuOpen(false)}
                className={({ isActive }) => `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${isActive ? 'bg-slate-800 text-cyan-300' : 'text-slate-300 hover:bg-slate-800 hover:text-white'}`}
              >
                <Tags className="h-4 w-4" /> Tags
              </NavLink>}
              {user.role === 'admin' && <NavLink to="/members" onClick={() => setIsMenuOpen(false)} className={({ isActive }) => `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${isActive ? 'bg-slate-800 text-cyan-300' : 'text-slate-300 hover:bg-slate-800 hover:text-white'}`}>
                <Users className="h-4 w-4" /> Members
              </NavLink>}
            </div>
            <div className="my-2 border-t border-slate-800" />
            {logoutError && <p role="alert" className="mb-2 rounded-md bg-rose-950/60 px-3 py-2 text-xs text-rose-300">{logoutError}</p>}
            <button
              type="button"
              onClick={handleLogout}
              disabled={isLoggingOut}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-rose-300 transition-colors hover:bg-rose-950/60 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              {isLoggingOut ? 'Logging out...' : 'Logout'}
            </button>
          </div>}
        </div>
      </div>
    </nav>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
            <NavBar />
            {/* Main content */}
            <main className="flex-1">
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route path="/change-password" element={<ProtectedRoute allowPasswordChange><ChangePasswordPage /></ProtectedRoute>} />
                <Route path="/" element={<ProtectedRoute><TargetListPage /></ProtectedRoute>} />
                <Route path="/tags" element={<ProtectedRoute adminOnly><TagsPage /></ProtectedRoute>} />
                <Route path="/members" element={<ProtectedRoute adminOnly><MembersPage /></ProtectedRoute>} />
                <Route path="/targets/:id" element={<ProtectedRoute><TargetDetailPage /></ProtectedRoute>} />
                <Route path="/checks/:id" element={<ProtectedRoute><CheckDetailPage /></ProtectedRoute>} />
              </Routes>
            </main>

            {/* Footer */}
            <footer className="py-6 border-t border-slate-900 text-center text-xs text-slate-600 mt-auto">
              &copy; {new Date().getFullYear()} Web Defacement Monitor. All rights reserved.
            </footer>
          </div>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}
