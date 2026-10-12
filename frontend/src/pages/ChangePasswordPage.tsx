import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, apiFetch } from '../api/client';
import { useAuth } from '../hooks/authContext';

export function ChangePasswordPage() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const { logout } = useAuth();
  const navigate = useNavigate();

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError('');
    if (next.length < 12) return setError('New password must be at least 12 characters.');
    if (next !== confirm) return setError('Passwords do not match.');
    setBusy(true);
    try {
      await apiFetch('/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: current, new_password: next }) });
      await logout();
      navigate('/login', { replace: true });
    } catch (e) { setError(e instanceof ApiError ? e.detail : 'Password change failed.'); }
    finally { setBusy(false); }
  }
  return <div className="min-h-screen flex items-center justify-center bg-slate-950 p-4"><section className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-8">
    <h1 className="text-2xl font-bold text-white">Change your password</h1><p className="mt-2 text-sm text-slate-400">Set a new password before continuing.</p>
    {error && <p role="alert" className="mt-4 text-sm text-rose-300">{error}</p>}
    <form onSubmit={submit} className="mt-6 space-y-4">
      <label className="block text-sm text-slate-300">Current password<input required type="password" value={current} onChange={e => setCurrent(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" /></label>
      <label className="block text-sm text-slate-300">New password<input required minLength={12} maxLength={200} type="password" value={next} onChange={e => setNext(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" /></label>
      <label className="block text-sm text-slate-300">Confirm new password<input required minLength={12} maxLength={200} type="password" value={confirm} onChange={e => setConfirm(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" /></label>
      <button disabled={busy} className="w-full rounded-lg bg-blue-600 px-4 py-2.5 font-semibold text-white disabled:opacity-50">{busy ? 'Saving…' : 'Change password'}</button>
    </form>
  </section></div>;
}
