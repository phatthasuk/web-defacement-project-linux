import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, apiFetch } from '../api/client';

export function RegisterPage() {
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    if (password.length < 12) return setError('Password must be at least 12 characters.');
    if (password !== confirmation) return setError('Passwords do not match.');
    setBusy(true);
    try {
      await apiFetch('/auth/register', { method: 'POST', body: JSON.stringify({ username, display_name: displayName, password, password_confirmation: confirmation }) });
      setSubmitted(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : 'Registration failed. Please try again.');
    } finally { setBusy(false); }
  }

  return <div className="min-h-screen flex items-center justify-center bg-slate-950 p-4">
    <section className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-8">
      {submitted ? <>
        <h1 className="text-2xl font-bold text-white">Registration submitted</h1>
        <p className="mt-3 text-slate-300">Registration submitted. Awaiting Admin approval.</p>
        <Link className="mt-6 inline-block text-cyan-400 hover:text-cyan-300" to="/login">Back to Login</Link>
      </> : <>
        <h1 className="text-2xl font-bold text-white">Create an Operator account</h1>
        <p className="mt-2 text-sm text-slate-400">An Admin must approve your registration before you can sign in.</p>
        {error && <p role="alert" className="mt-4 rounded border border-rose-800 bg-rose-950/50 p-3 text-sm text-rose-300">{error}</p>}
        <form onSubmit={submit} className="mt-6 space-y-4">
          <label className="block text-sm text-slate-300">Username<input required maxLength={50} value={username} onChange={e => setUsername(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" /></label>
          <label className="block text-sm text-slate-300">Display name<input required maxLength={100} value={displayName} onChange={e => setDisplayName(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" /></label>
          <label className="block text-sm text-slate-300">Password<input required minLength={12} maxLength={200} type="password" value={password} onChange={e => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" /></label>
          <label className="block text-sm text-slate-300">Confirm password<input required minLength={12} maxLength={200} type="password" value={confirmation} onChange={e => setConfirmation(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" /></label>
          <button disabled={busy} className="w-full rounded-lg bg-blue-600 px-4 py-2.5 font-semibold text-white disabled:opacity-50">{busy ? 'Submitting…' : 'Submit registration'}</button>
        </form>
        <p className="mt-5 text-center text-sm text-slate-400">Already registered? <Link className="text-cyan-400" to="/login">Sign in</Link></p>
      </>}
    </section>
  </div>;
}
