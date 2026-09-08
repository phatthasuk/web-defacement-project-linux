import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { BaselineManagerModal } from './BaselineManagerModal';
import { Snapshot } from '../types/snapshot';

const mockBaselines: Snapshot[] = [
  {
    id: 'snap-b1',
    target_id: 't-1',
    captured_at: '2026-09-03T07:30:00Z',
    final_url: 'https://example.com',
    http_status: 200,
    title: 'Hospital Home',
    is_baseline: true,
  },
  {
    id: 'snap-b2',
    target_id: 't-1',
    captured_at: '2026-09-03T07:35:00Z',
    final_url: 'https://example.com',
    http_status: 200,
    title: 'Hospital Home Promo',
    is_baseline: true,
  },
];

describe('BaselineManagerModal', () => {
  it('does not render when isOpen is false', () => {
    render(
      <BaselineManagerModal
        isOpen={false}
        onClose={vi.fn()}
        targetId="t-1"
        targetName="Test Target"
        baselines={mockBaselines}
        isLoading={false}
        onDemote={vi.fn()}
        isDemoting={false}
      />
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders active baselines count and cards when isOpen is true', () => {
    render(
      <BaselineManagerModal
        isOpen={true}
        onClose={vi.fn()}
        targetId="t-1"
        targetName="Test Target"
        latestMatchedSnapshotId="snap-b2"
        baselines={mockBaselines}
        isLoading={false}
        onDemote={vi.fn()}
        isDemoting={false}
      />
    );

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/2 \/ 20 Active/i)).toBeInTheDocument();
    expect(screen.getByText('snap-b1')).toBeInTheDocument();
    expect(screen.getByText('snap-b2')).toBeInTheDocument();
    expect(screen.getByText('Hospital Home Promo')).toBeInTheDocument();
    expect(screen.getByText(/Latest Match/i)).toBeInTheDocument();
  });

  it('prompts confirmation when Remove from Baselines is clicked, and calls onDemote on confirm', async () => {
    const onDemote = vi.fn().mockResolvedValue(undefined);
    render(
      <BaselineManagerModal
        isOpen={true}
        onClose={vi.fn()}
        targetId="t-1"
        targetName="Test Target"
        baselines={mockBaselines}
        isLoading={false}
        onDemote={onDemote}
        isDemoting={false}
      />
    );

    const removeButtons = screen.getAllByRole('button', { name: /Remove from Baselines/i });
    fireEvent.click(removeButtons[0]);

    expect(screen.getByText(/Remove this baseline from active rotation\?/i)).toBeInTheDocument();

    const confirmBtn = screen.getByRole('button', { name: /Confirm Remove/i });
    fireEvent.click(confirmBtn);

    expect(onDemote).toHaveBeenCalledWith('snap-b1');
  });

  it('cancels removal when Cancel is clicked', () => {
    render(
      <BaselineManagerModal
        isOpen={true}
        onClose={vi.fn()}
        targetId="t-1"
        targetName="Test Target"
        baselines={mockBaselines}
        isLoading={false}
        onDemote={vi.fn()}
        isDemoting={false}
      />
    );

    const removeButtons = screen.getAllByRole('button', { name: /Remove from Baselines/i });
    fireEvent.click(removeButtons[0]);

    expect(screen.getByText(/Remove this baseline from active rotation\?/i)).toBeInTheDocument();

    const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(cancelBtn);

    expect(screen.queryByText(/Remove this baseline from active rotation\?/i)).not.toBeInTheDocument();
  });

  it('calls onClose when close button or Done button is clicked', () => {
    const onClose = vi.fn();
    render(
      <BaselineManagerModal
        isOpen={true}
        onClose={onClose}
        targetId="t-1"
        targetName="Test Target"
        baselines={mockBaselines}
        isLoading={false}
        onDemote={vi.fn()}
        isDemoting={false}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Close baseline manager/i }));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: /Done/i }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  // --- The last baseline must not be removable ---------------------------------
  // With no baseline left, the next check adopts whatever the site is serving as
  // the new baseline and reports OK without review, so a defacement present at
  // that moment would become the reference silently.

  it('does not offer removal when only one baseline remains', () => {
    render(
      <BaselineManagerModal
        isOpen={true}
        onClose={vi.fn()}
        targetId="t-1"
        targetName="Test Target"
        baselines={[mockBaselines[0]]}
        isLoading={false}
        onDemote={vi.fn()}
        isDemoting={false}
      />
    );

    expect(screen.queryByText(/Remove from Baselines/i)).not.toBeInTheDocument();
    expect(screen.getByText(/only baseline and cannot be removed/i)).toBeInTheDocument();
  });

  it('surfaces the reason when a removal is rejected', async () => {
    const onDemote = vi.fn().mockRejectedValue(new Error('Cannot remove the only baseline'));

    render(
      <BaselineManagerModal
        isOpen={true}
        onClose={vi.fn()}
        targetId="t-1"
        targetName="Test Target"
        baselines={mockBaselines}
        isLoading={false}
        onDemote={onDemote}
        isDemoting={false}
      />
    );

    fireEvent.click(screen.getAllByRole('button', { name: /Remove from Baselines/i })[0]);
    fireEvent.click(screen.getByRole('button', { name: /Confirm Remove/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /Cannot remove the only baseline/i
    );
  });
});
