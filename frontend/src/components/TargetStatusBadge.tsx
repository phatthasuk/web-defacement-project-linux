import { TargetStatus } from '../types/target';

interface TargetStatusBadgeProps {
  status: TargetStatus;
  title?: string;
}

export function TargetStatusBadge({ status, title }: TargetStatusBadgeProps) {
  let badgeStyles = '';
  let dotStyles = '';
  const label = status;

  switch (status) {
    case 'Never Checked':
      badgeStyles = 'bg-slate-900/60 border border-slate-700/50 text-slate-400';
      dotStyles = 'bg-slate-500';
      break;
    case 'Checking':
      badgeStyles = 'bg-cyan-950/60 border border-cyan-800/50 text-cyan-400 font-medium shadow-[0_0_8px_rgba(34,211,238,0.15)]';
      dotStyles = 'bg-cyan-400 animate-pulse';
      break;
    case 'OK':
      badgeStyles = 'bg-emerald-950/60 border border-emerald-800/50 text-emerald-400 font-medium shadow-[0_0_8px_rgba(52,211,153,0.15)]';
      dotStyles = 'bg-emerald-400';
      break;
    case 'Changed':
      badgeStyles = 'bg-amber-950/60 border border-amber-850/50 text-amber-400 font-medium shadow-[0_0_8px_rgba(251,191,36,0.2)]';
      dotStyles = 'bg-amber-400';
      break;
    case 'Failed':
      badgeStyles = 'bg-rose-950/60 border border-rose-800/50 text-rose-400 font-medium shadow-[0_0_8px_rgba(251,113,133,0.2)]';
      dotStyles = 'bg-rose-500';
      break;
    case 'Acknowledged':
      badgeStyles = 'bg-indigo-950/60 border border-indigo-800/50 text-indigo-400 font-medium';
      dotStyles = 'bg-indigo-400';
      break;
    case 'Availability Issue':
      badgeStyles = 'bg-orange-950/60 border border-orange-800/50 text-orange-400 font-medium shadow-[0_0_8px_rgba(251,146,60,0.2)]';
      dotStyles = 'bg-orange-400';
      break;
    case 'Defaced':
      badgeStyles = 'bg-rose-950/80 border border-rose-600/70 text-rose-300 font-semibold shadow-[0_0_12px_rgba(244,63,94,0.35)]';
      dotStyles = 'bg-rose-500 animate-pulse';
      break;
    default:
      badgeStyles = 'bg-slate-900 border border-slate-800 text-slate-400';
      dotStyles = 'bg-slate-400';
  }

  return (
    <span title={title} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold tracking-wide transition-all duration-300 ${badgeStyles}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotStyles}`} />
      {label}
    </span>
  );
}
