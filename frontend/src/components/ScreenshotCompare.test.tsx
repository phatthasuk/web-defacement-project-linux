import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ScreenshotCompare } from './ScreenshotCompare';

describe('ScreenshotCompare', () => {
  beforeEach(() => {
    vi.mocked(globalThis.fetch).mockReset();
  });

  it('renders placeholders when snapshot IDs are missing', () => {
    render(<ScreenshotCompare baselineSnapshotId={null} currentSnapshotId={null} />);
    expect(screen.getByText(/No baseline snapshot designated/i)).toBeInTheDocument();
    expect(screen.getByText(/No checks run yet/i)).toBeInTheDocument();
  });

  it('renders image tags pointing to baseline and current snapshots', () => {
    render(<ScreenshotCompare baselineSnapshotId="b-123" currentSnapshotId="c-456" />);

    const baselineImg = screen.getByAltText('Baseline screenshot') as HTMLImageElement;
    const currentImg = screen.getByAltText('Latest screenshot') as HTMLImageElement;

    expect(baselineImg).toBeInTheDocument();
    expect(baselineImg.src).toContain('/snapshots/b-123/screenshot');

    expect(currentImg).toBeInTheDocument();
    expect(currentImg.src).toContain('/snapshots/c-456/screenshot');
  });

  it('renders 3-panel diff mode by default with the visual diff panel', () => {
    render(<ScreenshotCompare baselineSnapshotId="b-123" currentSnapshotId="c-456" />);

    expect(screen.getByText(/Baseline Screenshot/i)).toBeInTheDocument();
    expect(screen.getByText(/Visual Diff Highlight/i)).toBeInTheDocument();
    expect(screen.getByText(/Latest Screenshot/i)).toBeInTheDocument();
    expect(screen.getByText(/Red = Changed/i)).toBeInTheDocument();
  });

  it('allows toggling between 3-panel and side-by-side view modes', () => {
    render(<ScreenshotCompare baselineSnapshotId="b-123" currentSnapshotId="c-456" />);

    // Initially 3-panel
    expect(screen.getByText(/Visual Diff Highlight/i)).toBeInTheDocument();

    // Click Side-by-side
    fireEvent.click(screen.getByRole('button', { name: /Side-by-side/i }));
    expect(screen.queryByText(/Visual Diff Highlight/i)).not.toBeInTheDocument();

    // Click back to 3-panel
    fireEvent.click(screen.getByRole('button', { name: /3-Panel Diff/i }));
    expect(screen.getByText(/Visual Diff Highlight/i)).toBeInTheDocument();
  });

  // --- A screenshot that fails to load must not look like an unchanged page (Finding 4) ---

  it('shows an explicit error with retry when a screenshot fails to load', () => {
    render(<ScreenshotCompare baselineSnapshotId="b-123" currentSnapshotId="c-456" />);

    fireEvent.error(screen.getByAltText('Baseline screenshot'));

    expect(screen.getByText(/Screenshot failed to load/i)).toBeInTheDocument();
    expect(screen.getByText(/not evidence that the page is unchanged/i)).toBeInTheDocument();
    expect(screen.queryByAltText('Baseline screenshot')).not.toBeInTheDocument();

    // The other side is unaffected.
    expect(screen.getByAltText('Latest screenshot')).toBeInTheDocument();

    // Clicking Retry restores the image element for another load attempt
    const retryButtons = screen.getAllByRole('button', { name: /Retry/i });
    fireEvent.click(retryButtons[0]);
    expect(screen.getByAltText('Baseline screenshot')).toBeInTheDocument();
  });

  it('shows an explicit error with retry when visual diff heatmap calculation fails', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValue(new TypeError('Failed to fetch screenshot blob'));

    render(<ScreenshotCompare baselineSnapshotId="b-123" currentSnapshotId="c-456" />);

    await waitFor(() => {
      expect(screen.getByText(/Visual diff calculation failed/i)).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/Diff preview requires both baseline and latest captures/i)
    ).not.toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    const retryButton = screen.getByRole('button', { name: /Retry/i });
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(4);
    });
  });

  it('clears a previous load failure when the snapshot changes', () => {
    const { rerender } = render(
      <ScreenshotCompare baselineSnapshotId="b-123" currentSnapshotId="c-456" />
    );

    fireEvent.error(screen.getByAltText('Baseline screenshot'));
    expect(screen.getByText(/Screenshot failed to load/i)).toBeInTheDocument();

    rerender(<ScreenshotCompare baselineSnapshotId="b-789" currentSnapshotId="c-456" />);

    expect(screen.queryByText(/Screenshot failed to load/i)).not.toBeInTheDocument();
    const retriedImg = screen.getByAltText('Baseline screenshot') as HTMLImageElement;
    expect(retriedImg.src).toContain('/snapshots/b-789/screenshot');
  });

  // --- Click-to-Zoom Lightbox Modal ---

  it('opens zoom modal when clicking a screenshot panel and closes on close button', () => {
    render(<ScreenshotCompare baselineSnapshotId="b-123" currentSnapshotId="c-456" />);

    const baselineImg = screen.getByAltText('Baseline screenshot');
    fireEvent.click(baselineImg);

    // Modal should be open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Full-Resolution View/i)).toBeInTheDocument();

    // Close button
    const closeBtn = screen.getByRole('button', { name: /Close image zoom/i });
    fireEvent.click(closeBtn);

    // Modal should be closed
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes zoom modal on Escape key', () => {
    render(<ScreenshotCompare baselineSnapshotId="b-123" currentSnapshotId="c-456" />);

    fireEvent.click(screen.getByAltText('Latest screenshot'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
