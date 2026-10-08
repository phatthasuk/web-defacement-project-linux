import { Link } from 'react-router-dom';
import { TagBadge } from './TagBadge';
import type { Tag } from '../types/tag';

interface TagMultiSelectProps {
  tags: Tag[];
  selectedIds: string[];
  onChange: (tagIds: string[]) => void;
  disabled?: boolean;
  label?: string;
}

export function TagMultiSelect({ tags, selectedIds, onChange, disabled = false, label = 'Tags' }: TagMultiSelectProps) {
  const selected = new Set(selectedIds);
  const toggle = (tagId: string) => {
    onChange(selected.has(tagId) ? selectedIds.filter((id) => id !== tagId) : [...selectedIds, tagId]);
  };

  return (
    <fieldset disabled={disabled}>
      <div className="mb-2 flex items-center justify-between gap-3">
        <legend className="text-sm font-medium text-slate-300">{label}</legend>
        <Link to="/tags" className="text-xs font-medium text-cyan-400 hover:text-cyan-300">Manage Tags</Link>
      </div>
      {tags.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-700 px-3 py-2 text-xs text-slate-500">
          No tags yet. Create one in Manage Tags.
        </p>
      ) : (
        <div className="flex max-h-36 flex-wrap gap-2 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950/60 p-2">
          {tags.map((tag) => (
            <label key={tag.id} className="cursor-pointer">
              <input
                type="checkbox"
                className="peer sr-only"
                checked={selected.has(tag.id)}
                onChange={() => toggle(tag.id)}
              />
              <span className="block rounded-full opacity-55 transition peer-checked:opacity-100 peer-focus-visible:ring-2 peer-focus-visible:ring-cyan-400">
                <TagBadge tag={tag} />
              </span>
            </label>
          ))}
        </div>
      )}
    </fieldset>
  );
}
