import { StrictMode } from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getTarget } from '../api/targets';
import { listTargetChecks } from '../api/checks';
import {
  getSnapshotText, getTargetBaselineSnapshot, listTargetBaselines, listTargetSnapshots,
} from '../api/snapshots';
import { Target } from '../types/target';
import { Snapshot } from '../types/snapshot';
import { CheckResult } from '../types/checkResult';
import { TargetDetailPage } from './TargetDetailPage';

// Keep real query hooks and cache observers; only replace the API boundary.
vi.mock('../api/targets', () => ({ getTarget: vi.fn() }));
vi.mock('../api/checks', () => ({ listTargetChecks: vi.fn() }));
vi.mock('../api/snapshots', () => ({
  getSnapshotText: vi.fn(),
  getTargetBaselineSnapshot: vi.fn(),
  listTargetBaselines: vi.fn(),
  listTargetSnapshots: vi.fn(),
}));
// Image decoding/canvas has its own tests. Expose the snapshot IDs sent to it.
vi.mock('../components/ScreenshotCompare', () => ({
  ScreenshotCompare: ({ baselineSnapshotId, currentSnapshotId }: {
    baselineSnapshotId?: string; currentSnapshotId?: string;
  }) => <div data-testid="screenshot-pair">{baselineSnapshotId}|{currentSnapshotId}</div>,
}));

function makeState(targetId: string, revision = 1) {
  const timestamp = `2026-09-08T0${revision}:00:00Z`;
  const target: Target = {
    id: targetId, name: targetId, url: 'https://example.com', status: 'Changed',
    is_active: true, last_error: null, created_at: timestamp, updated_at: timestamp,
  };
  const baseline: Snapshot = {
    id: `${targetId}-baseline-${revision}`, target_id: targetId, captured_at: timestamp,
    final_url: target.url, http_status: 200, title: 'Baseline', is_baseline: true,
  };
  const current: Snapshot = { ...baseline, id: `${targetId}-current-${revision}`, is_baseline: false };
  const check: CheckResult = {
    id: `${targetId}-check-${revision}`, target_id: targetId,
    baseline_snapshot_id: baseline.id, current_snapshot_id: current.id,
    created_at: timestamp, status: 'Changed', text_change_score: 0.1,
    visual_change_score: 0.1, structure_change_score: 0, summary: 'Changed',
    acknowledged_at: null,
  };
  return { target, baseline, current, check };
}

type ServerState = ReturnType<typeof makeState>;
let client: QueryClient;
let server: Map<string, ServerState>;
let router: ReturnType<typeof createMemoryRouter>;

function seed(state: ServerState) {
  const id = state.target.id;
  client.setQueryData(['targets', id], state.target);
  client.setQueryData(['checks', id], [state.check]);
  client.setQueryData(['snapshots', id], [state.current, state.baseline]);
  client.setQueryData(['baseline', id], state.baseline);
  client.setQueryData(['baselines', id], [state.baseline]);
  client.setQueryData(['snapshotText', state.baseline.id], 'baseline text');
  client.setQueryData(['snapshotText', state.current.id], 'current text');
}

function openPage(strict = false) {
  router = createMemoryRouter([
    { path: '/targets/:id', element: <TargetDetailPage /> },
  ], { initialEntries: ['/targets/target-1'] });
  const view = <QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>;
  render(strict ? <StrictMode>{view}</StrictMode> : view);
}

async function expectPair(state: ServerState) {
  await waitFor(() => expect(screen.getByTestId('screenshot-pair'))
    .toHaveTextContent(`${state.baseline.id}|${state.current.id}`));
}

async function publishResult(state: ServerState, checkOnly = false) {
  server.set(state.target.id, state);
  // Publish the same metadata that a polling response would put into the cache.
  await act(async () => {
    if (!checkOnly) client.setQueryData(['targets', state.target.id], state.target);
    client.setQueryData(['checks', state.target.id], [state.check]);
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } });
  server = new Map(['target-1', 'target-2'].map((id) => [id, makeState(id)]));
  client.setQueryData(['config'], {
    text_change_threshold: 0.02, visual_change_threshold: 0.01,
    structure_change_threshold: 0, max_baselines_per_target: 20,
  });
  vi.mocked(getTarget).mockImplementation(async (id) => server.get(id)!.target);
  vi.mocked(listTargetChecks).mockImplementation(async (id) => [server.get(id)!.check]);
  vi.mocked(listTargetSnapshots).mockImplementation(async (id) => {
    const state = server.get(id)!;
    return [state.current, state.baseline];
  });
  vi.mocked(getTargetBaselineSnapshot).mockImplementation(async (id) => server.get(id)!.baseline);
  vi.mocked(listTargetBaselines).mockImplementation(async (id) => [server.get(id)!.baseline]);
  vi.mocked(getSnapshotText).mockImplementation(async (id) => `text for ${id}`);
});

afterEach(() => {
  cleanup();
  router?.dispose();
  client.clear();
});

describe('TargetDetailPage cache refresh', () => {
  it.each([false, true])('refreshes the first result after a cached mount (StrictMode=%s)', async (strict) => {
    seed(server.get('target-1')!);
    openPage(strict);
    await expectPair(server.get('target-1')!);
    expect(listTargetSnapshots).not.toHaveBeenCalled();

    const next = makeState('target-1', 2);
    // No Checking response is observed, and the final status remains Changed.
    await publishResult(next);
    await expectPair(next);
    expect(getTargetBaselineSnapshot).toHaveBeenCalledWith('target-1');
    expect(listTargetBaselines).toHaveBeenCalledWith('target-1');
    await waitFor(() => expect(getSnapshotText).toHaveBeenCalledWith(next.current.id));
    expect(getSnapshotText).toHaveBeenCalledWith(next.baseline.id);
  });

  it('refreshes when only the latest check changes between polls', async () => {
    seed(server.get('target-1')!);
    openPage();
    const next = makeState('target-1', 2);
    await publishResult(next, true);
    await expectPair(next);
  });

  it('still refreshes after initially loading without cached target data', async () => {
    openPage();
    await expectPair(server.get('target-1')!);
    const next = makeState('target-1', 2);
    await publishResult(next);
    await expectPair(next);
  });

  it('tracks the new target and a return to the previous target independently', async () => {
    for (const state of server.values()) seed(state);
    openPage();
    await expectPair(server.get('target-1')!);

    await act(async () => { await router.navigate('/targets/target-2'); });
    await expectPair(server.get('target-2')!);
    expect(listTargetSnapshots).not.toHaveBeenCalled();

    const second = makeState('target-2', 2);
    await publishResult(second);
    await expectPair(second);
    expect(vi.mocked(listTargetSnapshots).mock.calls.every(([id]) => id === 'target-2')).toBe(true);
    await waitFor(() => expect(client.isFetching()).toBe(0));
    vi.mocked(listTargetSnapshots).mockClear();

    await act(async () => { await router.navigate('/targets/target-1'); });
    await expectPair(server.get('target-1')!);
    expect(listTargetSnapshots).not.toHaveBeenCalled();
    const first = makeState('target-1', 2);
    await publishResult(first);
    await expectPair(first);
    expect(vi.mocked(listTargetSnapshots).mock.calls.every(([id]) => id === 'target-1')).toBe(true);
  });

  it('does not refetch artifacts when metadata is unchanged', async () => {
    const current = server.get('target-1')!;
    seed(current);
    openPage(true);
    await publishResult({ ...current, target: { ...current.target }, check: { ...current.check } });
    await expectPair(current);
    expect(listTargetSnapshots).not.toHaveBeenCalled();
    expect(getTargetBaselineSnapshot).not.toHaveBeenCalled();
    expect(listTargetBaselines).not.toHaveBeenCalled();
    expect(getSnapshotText).not.toHaveBeenCalled();
  });
});
