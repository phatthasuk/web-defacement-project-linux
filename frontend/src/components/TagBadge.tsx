import type { Tag } from '../types/tag';

const colorClasses: Record<Tag['color_key'], string> = {
  cyan: 'bg-cyan-950/70 border-cyan-700/70 text-cyan-300',
  blue: 'bg-blue-950/70 border-blue-700/70 text-blue-300',
  violet: 'bg-violet-950/70 border-violet-700/70 text-violet-300',
  emerald: 'bg-emerald-950/70 border-emerald-700/70 text-emerald-300',
  amber: 'bg-amber-950/70 border-amber-700/70 text-amber-300',
  rose: 'bg-rose-950/70 border-rose-700/70 text-rose-300',
  slate: 'bg-slate-800 border-slate-600 text-slate-300',
};

export function TagBadge({ tag }: { tag: Pick<Tag, 'name' | 'color_key'> }) {
  return (
    <span
      title={tag.name}
      className={`inline-flex max-w-40 items-center rounded-full border px-2 py-0.5 text-xs font-medium ${colorClasses[tag.color_key]}`}
    >
      <span className="truncate">{tag.name}</span>
    </span>
  );
}
