import { useState, useEffect, useCallback } from 'react';
import { BASE_URL } from '../api/client';

interface ScreenshotCompareProps {
  baselineSnapshotId?: string | null;
  currentSnapshotId?: string | null;
}

interface ScreenshotPanelProps {
  label: string;
  alt: string;
  src?: string | null;
  emptyMessage: string;
  isLoading?: boolean;
  badge?: string;
  badgeColor?: string;
  onZoom?: (src: string, label: string) => void;
}

const panelFrameClass =
  'border border-slate-800 rounded-lg overflow-hidden bg-slate-900 flex items-center justify-center min-h-[200px] relative group';

/**
 * Loads an image from a URL with session credentials included and returns an HTMLImageElement.
 */
async function loadAuthenticatedImage(url: string): Promise<HTMLImageElement> {
  const response = await fetch(url, { credentials: 'include' }).catch(() => null);
  if (!response || !response.ok) {
    throw new Error(`Failed to load image from ${url}`);
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);

  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error(`Failed to decode image from ${url}`));
    };
    img.src = objectUrl;
  });
}

/**
 * Generates a visual diff highlight heatmap on an offscreen HTML5 canvas.
 * Unchanged pixels are desaturated/dimmed, while changed pixels glow in vivid neon red.
 */
function computeDiffHeatmap(
  baselineImg: HTMLImageElement,
  currentImg: HTMLImageElement
): string | null {
  const width = Math.max(baselineImg.naturalWidth || baselineImg.width, currentImg.naturalWidth || currentImg.width);
  const height = Math.max(baselineImg.naturalHeight || baselineImg.height, currentImg.naturalHeight || currentImg.height);

  if (!width || !height) return null;

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  // Draw current image onto main canvas
  ctx.drawImage(currentImg, 0, 0);
  const currentData = ctx.getImageData(0, 0, width, height);

  // Draw baseline image onto temporary canvas
  const tempCanvas = document.createElement('canvas');
  tempCanvas.width = width;
  tempCanvas.height = height;
  const tempCtx = tempCanvas.getContext('2d');
  if (!tempCtx) return null;

  tempCtx.drawImage(baselineImg, 0, 0);
  const baselineData = tempCtx.getImageData(0, 0, width, height);

  const cur = currentData.data;
  const base = baselineData.data;
  const len = cur.length;

  for (let i = 0; i < len; i += 4) {
    const rDiff = Math.abs(cur[i] - base[i]);
    const gDiff = Math.abs(cur[i + 1] - base[i + 1]);
    const bDiff = Math.abs(cur[i + 2] - base[i + 2]);

    // Sensitivity threshold: ignore sub-pixel anti-aliasing (<10)
    if (rDiff > 10 || gDiff > 10 || bDiff > 10) {
      // Vivid Neon Red highlight for altered pixels
      cur[i] = 239;     // Red
      cur[i + 1] = 68;  // Green
      cur[i + 2] = 68;  // Blue
      cur[i + 3] = 255; // Alpha
    } else {
      // Dim unchanged content so highlights immediately catch the eye
      const gray = cur[i] * 0.299 + cur[i + 1] * 0.587 + cur[i + 2] * 0.114;
      cur[i] = Math.round(gray * 0.7);
      cur[i + 1] = Math.round(gray * 0.7);
      cur[i + 2] = Math.round(gray * 0.7);
      cur[i + 3] = 210;
    }
  }

  ctx.putImageData(currentData, 0, 0);
  return canvas.toDataURL('image/png');
}

/**
 * Individual Screenshot Panel with Click-to-Zoom capability and failure boundaries.
 */
function ScreenshotPanel({
  label,
  alt,
  src,
  emptyMessage,
  isLoading,
  badge,
  badgeColor = 'bg-slate-800 text-slate-400 border-slate-700',
  onZoom,
}: ScreenshotPanelProps) {
  const [hasFailed, setHasFailed] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{label}</span>
        {badge && (
          <span className={`text-[10px] px-2 py-0.5 rounded-full border ${badgeColor} font-mono`}>
            {badge}
          </span>
        )}
      </div>

      {!src && !isLoading ? (
        <div className="border border-slate-800 border-dashed rounded-lg bg-slate-950/40 p-10 text-center text-slate-500 text-sm flex items-center justify-center min-h-[200px]">
          {emptyMessage}
        </div>
      ) : isLoading ? (
        <div className="border border-slate-800 rounded-lg bg-slate-900/60 p-10 text-center text-slate-400 text-sm flex flex-col items-center justify-center gap-3 min-h-[200px]">
          <svg className="animate-spin h-6 w-6 text-cyan-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span>Rendering visual comparison...</span>
        </div>
      ) : hasFailed ? (
        <div
          role="alert"
          className="border border-rose-800/40 rounded-lg bg-rose-950/20 p-10 text-center text-sm flex flex-col items-center justify-center gap-1 min-h-[200px]"
        >
          <span className="font-semibold text-rose-400">Screenshot failed to load</span>
          <span className="text-slate-400 text-xs">
            This image is unavailable — not evidence that the page is unchanged.
          </span>
        </div>
      ) : (
        <div
          className={`${panelFrameClass} cursor-zoom-in`}
          onClick={() => src && onZoom?.(src, label)}
          title="Click to view full size"
        >
          <img
            src={src || undefined}
            alt={alt}
            className="max-w-full h-auto object-contain transition-transform duration-300 group-hover:scale-[1.01]"
            loading="lazy"
            onError={() => setHasFailed(true)}
          />
          <div className="absolute inset-0 bg-slate-950/0 group-hover:bg-slate-950/20 transition-colors flex items-center justify-center pointer-events-none">
            <span className="opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900/90 text-cyan-300 text-xs font-medium px-3 py-1.5 rounded-full border border-cyan-800/60 shadow-lg flex items-center gap-1.5 backdrop-blur-sm">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7" />
              </svg>
              Click to Expand
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export function ScreenshotCompare({
  baselineSnapshotId,
  currentSnapshotId,
}: ScreenshotCompareProps) {
  const [viewMode, setViewMode] = useState<'3-panel' | 'side-by-side'>('3-panel');
  const [diffUrl, setDiffUrl] = useState<string | null>(null);
  const [isDiffLoading, setIsDiffLoading] = useState(false);
  const [zoomedImage, setZoomedImage] = useState<{ src: string; label: string } | null>(null);

  const isSameSnapshot =
    !!baselineSnapshotId &&
    !!currentSnapshotId &&
    baselineSnapshotId === currentSnapshotId;

  // Handle ESC key to close zoom modal
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      setZoomedImage(null);
    }
  }, []);

  useEffect(() => {
    if (zoomedImage) {
      window.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    } else {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [zoomedImage, handleKeyDown]);

  // Compute visual diff on client canvas
  useEffect(() => {
    if (!baselineSnapshotId || !currentSnapshotId || isSameSnapshot) {
      setDiffUrl(null);
      setIsDiffLoading(false);
      return;
    }

    let isMounted = true;
    setIsDiffLoading(true);

    const baselineUrl = `${BASE_URL}/snapshots/${baselineSnapshotId}/screenshot`;
    const currentUrl = `${BASE_URL}/snapshots/${currentSnapshotId}/screenshot`;

    Promise.all([loadAuthenticatedImage(baselineUrl), loadAuthenticatedImage(currentUrl)])
      .then(([baseImg, curImg]) => {
        if (!isMounted) return;
        const diffDataUrl = computeDiffHeatmap(baseImg, curImg);
        setDiffUrl(diffDataUrl);
      })
      .catch(() => {
        if (isMounted) setDiffUrl(null);
      })
      .finally(() => {
        if (isMounted) setIsDiffLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [baselineSnapshotId, currentSnapshotId, isSameSnapshot]);

  const baselineSrc = baselineSnapshotId ? `${BASE_URL}/snapshots/${baselineSnapshotId}/screenshot` : null;
  const currentSrc = currentSnapshotId ? `${BASE_URL}/snapshots/${currentSnapshotId}/screenshot` : null;

  return (
    <div className="bg-slate-950/80 border border-slate-800/80 rounded-xl overflow-hidden shadow-inner">
      {/* Header with View Mode Switcher */}
      <div className="bg-slate-900/60 px-4 py-3 border-b border-slate-800/80 text-slate-300 font-semibold flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span>Screenshot Comparison</span>
          <span className="text-xs text-slate-500 font-normal">
            (Click any image to inspect full size)
          </span>
        </div>

        <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
          <button
            type="button"
            onClick={() => setViewMode('3-panel')}
            className={`text-xs px-3 py-1 rounded-md transition-all font-medium ${
              viewMode === '3-panel'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            3-Panel Diff (Heatmap)
          </button>
          <button
            type="button"
            onClick={() => setViewMode('side-by-side')}
            className={`text-xs px-3 py-1 rounded-md transition-all font-medium ${
              viewMode === 'side-by-side'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
            }`}
          >
            Side-by-side
          </button>
        </div>
      </div>

      {/* Grid Panels */}
      <div
        className={`grid gap-6 p-6 ${
          viewMode === '3-panel'
            ? 'grid-cols-1 lg:grid-cols-3'
            : 'grid-cols-1 md:grid-cols-2'
        }`}
      >
        {/* Panel 1: Baseline */}
        <ScreenshotPanel
          key={`baseline-${baselineSnapshotId ?? 'none'}`}
          label="Baseline Screenshot"
          alt="Baseline screenshot"
          src={baselineSrc}
          emptyMessage="No baseline snapshot designated yet."
          onZoom={(src, label) => setZoomedImage({ src, label })}
        />

        {/* Panel 2: Diff Highlight (Only in 3-panel view) */}
        {viewMode === '3-panel' && (
          <ScreenshotPanel
            key={`diff-${baselineSnapshotId}-${currentSnapshotId}`}
            label="Visual Diff Highlight"
            alt="Visual diff highlight"
            src={diffUrl}
            isLoading={isDiffLoading}
            badge="Red = Changed"
            badgeColor="bg-rose-950/60 text-rose-400 border-rose-800/50"
            emptyMessage={
              isSameSnapshot
                ? 'Snapshots are identical (No visual changes)'
                : 'Diff preview requires both baseline and latest captures'
            }
            onZoom={(src, label) => setZoomedImage({ src, label })}
          />
        )}

        {/* Panel 3: Latest */}
        <ScreenshotPanel
          key={`current-${currentSnapshotId ?? 'none'}`}
          label="Latest Screenshot"
          alt="Latest screenshot"
          src={currentSrc}
          emptyMessage="No checks run yet."
          onZoom={(src, label) => setZoomedImage({ src, label })}
        />
      </div>

      {/* Fullscreen Zoom Lightbox Modal */}
      {zoomedImage && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={zoomedImage.label}
          className="fixed inset-0 z-50 bg-slate-950/90 backdrop-blur-md flex flex-col p-4 md:p-6"
          onClick={() => setZoomedImage(null)}
        >
          {/* Modal Top Bar */}
          <div
            className="flex items-center justify-between pb-3 border-b border-slate-800 text-slate-200 shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <h3 className="font-semibold text-lg text-slate-100">{zoomedImage.label}</h3>
              <span className="text-xs bg-slate-800 border border-slate-700 text-slate-400 px-2 py-0.5 rounded">
                Full-Resolution View
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-500 hidden sm:inline">Press Esc or click outside to close</span>
              <button
                type="button"
                onClick={() => setZoomedImage(null)}
                aria-label="Close image zoom"
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Modal Scrollable Image Container */}
          <div
            className="flex-1 overflow-auto mt-4 flex justify-center items-start cursor-zoom-out p-2"
            onClick={() => setZoomedImage(null)}
          >
            <img
              src={zoomedImage.src}
              alt={zoomedImage.label}
              className="max-w-none w-auto max-h-none rounded-lg shadow-2xl border border-slate-800/80 cursor-default"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </div>
  );
}
