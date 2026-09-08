import { diffLines } from 'diff';

interface TextDiffViewProps {
  baselineText: string;
  currentText: string;
}

export function TextDiffView({ baselineText, currentText }: TextDiffViewProps) {
  if (baselineText === currentText) {
    return (
      <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-6 text-center text-slate-500 font-mono text-sm">
        No textual differences detected. Both snapshots contain identical content.
      </div>
    );
  }

  const changes = diffLines(baselineText, currentText);

  return (
    <div className="bg-slate-950/80 border border-slate-800/80 rounded-xl overflow-hidden font-mono text-xs shadow-inner">
      <div className="bg-slate-900/60 px-4 py-2 border-b border-slate-800/80 text-slate-400 font-semibold flex items-center justify-between">
        <span>Text Content Diff</span>
        <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full border border-slate-700/50">
          Client-side Rendered
        </span>
      </div>
      <div className="p-4 max-h-[500px] overflow-y-auto">
        {changes.map((change, index) => {
          const lines = change.value.split('\n');
          // Remove trailing empty line if split created one
          if (lines.length > 1 && lines[lines.length - 1] === '') {
            lines.pop();
          }

          return (
            <div key={index} className="py-0.5">
              {lines.map((line, lineIndex) => {
                if (change.added) {
                  return (
                    <pre
                      key={lineIndex}
                      className="bg-emerald-950/40 text-emerald-400 px-3 py-1 rounded border-l-2 border-emerald-500 whitespace-pre-wrap leading-relaxed block"
                    >
                      + {line}
                    </pre>
                  );
                }
                if (change.removed) {
                  return (
                    <pre
                      key={lineIndex}
                      className="bg-rose-950/40 text-rose-400 px-3 py-1 rounded border-l-2 border-rose-500 whitespace-pre-wrap leading-relaxed block"
                    >
                      - {line}
                    </pre>
                  );
                }
                return (
                  <pre
                    key={lineIndex}
                    className="text-slate-400 px-3 py-1 pl-4 whitespace-pre-wrap leading-relaxed block"
                  >
                    {line}
                  </pre>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
