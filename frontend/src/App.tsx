import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TargetListPage } from './pages/TargetListPage';
import { TargetDetailPage } from './pages/TargetDetailPage';
import { CheckDetailPage } from './pages/CheckDetailPage';
import { LoginPage } from './pages/LoginPage';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { LogOut } from 'lucide-react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
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

  return <>{children}</>;
}

function NavBar() {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <nav className="bg-slate-900 border-b border-slate-800 px-6 py-3 flex justify-between items-center sticky top-0 z-10">
      <div className="font-bold text-lg text-slate-100 tracking-tight">
        Web Defacement Monitor
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-slate-400">
          Welcome, <span className="text-slate-200 font-medium">{user.username}</span>
        </span>
        <button
          onClick={logout}
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors bg-slate-800 hover:bg-slate-700 px-3 py-1.5 rounded-lg border border-slate-700 hover:border-slate-600"
        >
          <LogOut className="w-4 h-4" />
          Logout
        </button>
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
                <Route path="/" element={<ProtectedRoute><TargetListPage /></ProtectedRoute>} />
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
