interface ArtifactErrorProps {
  /** What could not be shown, e.g. "Text comparison unavailable". */
  title: string;
  /** Human-readable names of the artifacts that failed to load. */
  failedArtifacts: string[];
  onRetry?: () => void;
  isRetrying?: boolean;
}

/**
 * Shown when a snapshot artifact fails to load.
 *
 * A retrieval failure must never be rendered as "unchanged" — for a defacement
 * monitor that would report a target as safe when its content is simply unknown.
 */
export function ArtifactError({
  title,
  failedArtifacts,
  onRetry,
  isRetrying = false,
}: ArtifactErrorProps) {
  return (
    <div
      role="alert"
      className="bg-rose-950/20 border border-rose-800/40 rounded-xl p-6 flex flex-col sm:flex-row sm:items-center gap-4"
    >
      <svg
        className="h-6 w-6 shrink-0 text-rose-400"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>

      <div className="flex-1">
        <span className="font-semibold text-rose-400 block mb-1">{title}</span>
        <p className="text-slate-400 text-sm">
          Failed to load {failedArtifacts.join(' and ')}. This comparison is unknown — it is
          <span className="text-slate-300 font-semibold"> not </span>
          confirmation that the content is unchanged.
        </p>
      </div>

      {onRetry && (
        <button
          onClick={onRetry}
          disabled={isRetrying}
          className="shrink-0 bg-rose-900/40 hover:bg-rose-900/60 border border-rose-800/50 text-rose-200 font-semibold text-sm rounded-lg px-4 py-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isRetrying ? 'Retrying...' : 'Retry'}
        </button>
      )}
    </div>
  );
}
