import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TargetListPage } from './TargetListPage';
import * as useTargetsHooks from '../hooks/useTargets';

// Mock the hooks
vi.mock('../hooks/useTargets', () => ({
  useTargetsQuery: vi.fn(),
  usePaginatedTargetsQuery: vi.fn(),
  useCreateTargetMutation: vi.fn(),
  useUpdateTargetMutation: vi.fn(),
  useDeleteTargetMutation: vi.fn(),
  useTriggerCheckMutation: vi.fn(),
}));

describe('TargetListPage', () => {
  const mockTargets = [
    {
      id: 'target-1',
      name: 'Google',
      url: 'https://google.com',
      status: 'OK' as const,
      is_active: true,
      created_at: '2026-07-02T00:00:00Z',
      updated_at: '2026-07-02T01:00:00Z',
    },
    {
      id: 'target-2',
      name: 'Example',
      url: 'https://example.com',
      status: 'Never Checked' as const,
      is_active: true,
      created_at: '2026-07-02T00:00:00Z',
      updated_at: '2026-07-02T01:00:00Z',
    },
  ];

  const mockMutateAsyncCreate = vi.fn();
  const mockMutateAsyncUpdate = vi.fn();
  const mockMutateAsyncDelete = vi.fn();
  const mockMutateAsyncTrigger = vi.fn().mockResolvedValue({ target_id: 'target-2', accepted: true });

  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(useTargetsHooks.useTargetsQuery).mockReturnValue({
      data: mockTargets,
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useTargetsHooks.useTargetsQuery>);

    vi.mocked(useTargetsHooks.usePaginatedTargetsQuery).mockReturnValue({
      data: {
        items: mockTargets,
        total: mockTargets.length,
        limit: 50,
        offset: 0,
      },
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof useTargetsHooks.usePaginatedTargetsQuery>);

    vi.mocked(useTargetsHooks.useCreateTargetMutation).mockReturnValue({
      mutateAsync: mockMutateAsyncCreate,
      isPending: false,
    } as unknown as ReturnType<typeof useTargetsHooks.useCreateTargetMutation>);

    vi.mocked(useTargetsHooks.useUpdateTargetMutation).mockReturnValue({
      mutateAsync: mockMutateAsyncUpdate,
      isPending: false,
    } as unknown as ReturnType<typeof useTargetsHooks.useUpdateTargetMutation>);

    vi.mocked(useTargetsHooks.useDeleteTargetMutation).mockReturnValue({
      mutateAsync: mockMutateAsyncDelete,
      isPending: false,
    } as unknown as ReturnType<typeof useTargetsHooks.useDeleteTargetMutation>);

    vi.mocked(useTargetsHooks.useTriggerCheckMutation).mockReturnValue({
      mutateAsync: mockMutateAsyncTrigger,
      isPending: false,
    } as unknown as ReturnType<typeof useTargetsHooks.useTriggerCheckMutation>);
  });

  it('renders targets correctly', () => {
    render(
      <BrowserRouter>
        <TargetListPage />
      </BrowserRouter>
    );

    expect(screen.getByText('Web Defacement Monitor')).toBeInTheDocument();
    expect(screen.getByText('Google')).toBeInTheDocument();
    expect(screen.getByText('https://google.com')).toBeInTheDocument();
    expect(screen.getByText('Example')).toBeInTheDocument();
    expect(screen.getByText('https://example.com')).toBeInTheDocument();
  });

  it('calls createTarget when submitting form', async () => {
    render(
      <BrowserRouter>
        <TargetListPage />
      </BrowserRouter>
    );

    const nameInput = screen.getByLabelText('Target Name');
    const urlInput = screen.getByLabelText('Target URL');
    const submitBtn = screen.getByRole('button', { name: /Add Target/i });

    fireEvent.change(nameInput, { target: { value: 'New Site' } });
    fireEvent.change(urlInput, { target: { value: 'https://newsite.com' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockMutateAsyncCreate).toHaveBeenCalledWith({
        name: 'New Site',
        url: 'https://newsite.com',
      });
    });
  });

  it('calls triggerCheck when clicking Run Check button', async () => {
    render(
      <BrowserRouter>
        <TargetListPage />
      </BrowserRouter>
    );

    const checkBtn = screen.getByTestId('run-check-target-2');
    fireEvent.click(checkBtn);

    await waitFor(() => {
      expect(mockMutateAsyncTrigger).toHaveBeenCalledWith('target-2');
    });
  });

  it('opens edit modal and calls updateTarget when submitted', async () => {
    render(
      <BrowserRouter>
        <TargetListPage />
      </BrowserRouter>
    );

    const editBtn = screen.getByTestId('edit-target-target-1');
    fireEvent.click(editBtn);

    const dialog = screen.getByRole('dialog', { name: /Edit Target Google/i });
    expect(dialog).toBeInTheDocument();
    const nameInput = within(dialog).getByLabelText('Target Name');
    const urlInput = within(dialog).getByLabelText('Target URL');
    expect(nameInput).toHaveValue('Google');
    expect(urlInput).toHaveValue('https://google.com');

    fireEvent.change(nameInput, { target: { value: 'Google Thailand' } });
    fireEvent.change(urlInput, { target: { value: 'https://google.co.th' } });

    const saveBtn = within(dialog).getByRole('button', { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockMutateAsyncUpdate).toHaveBeenCalledWith({
        targetId: 'target-1',
        payload: {
          name: 'Google Thailand',
          url: 'https://google.co.th',
        },
      });
    });
  });

  it('opens delete modal and calls deleteTarget when confirmed', async () => {
    render(
      <BrowserRouter>
        <TargetListPage />
      </BrowserRouter>
    );

    const deleteBtn = screen.getByTestId('delete-target-target-1');
    fireEvent.click(deleteBtn);

    expect(screen.getByRole('dialog', { name: /Delete Target Google/i })).toBeInTheDocument();
    expect(screen.getByText(/Are you sure you want to delete/i)).toBeInTheDocument();

    const confirmBtn = screen.getByRole('button', { name: /Delete Target/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockMutateAsyncDelete).toHaveBeenCalledWith('target-1');
    });
  });
});
