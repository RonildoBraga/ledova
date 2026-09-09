// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), setActions: vi.fn() }));
vi.mock('@services/apiClient', () => ({ default: api }));
vi.mock('@hooks/useSelectedPortfolio', () => ({
  useSelectedPortfolio: () => ({ portfolio: { userAccount: 'owner' } }),
}));
vi.mock('@hooks/useHeaderActions', () => ({ useHeaderActions: () => ({ setActions: api.setActions }) }));
vi.mock('@hooks/useCurrency', () => ({
  useCurrency: () => ({ formatDisplayCurrency: (value: number) => `$${value}` }),
}));

import { WalletsPage } from './index';

const wallet = {
  uuid: 'wallet-1',
  userAccount: 'owner',
  name: 'Sync wallet',
  address: `0x${'3'.repeat(40)}`,
  chain: 'base',
  verificationStatus: 'VERIFIED',
  nativeBalance: '5',
  marketValue: '10',
};
let queryClient: QueryClient;

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  api.get.mockResolvedValue({ data: { results: [wallet], count: 1, next: null, previous: null } });
  api.post.mockReset();
});

afterEach(() => {
  cleanup();
  queryClient.clear();
});

describe('wallet sync feedback through the real service and mutation', () => {
  it('keeps an error attached to the failed wallet when the selection changes', async () => {
    const other = { ...wallet, uuid: 'wallet-2', name: 'Other wallet', chain: 'ethereum' };
    api.get.mockResolvedValue({ data: { results: [wallet, other], count: 2, next: null, previous: null } });
    const error = 'Some wallet balances could not be refreshed. Please try again later.';
    api.post.mockResolvedValueOnce({ data: { success: false, wallet, syncResult: { status: 'error', error } } });
    render(
      <QueryClientProvider client={queryClient}>
        <WalletsPage />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByText('Sync wallet'));
    fireEvent.click(
      screen.getAllByRole('button', { name: 'Sync' }).find((button) => !button.hasAttribute('disabled'))!,
    );
    expect((await screen.findByRole('alert')).textContent).toBe(error);
    fireEvent.click(screen.getByText('Other wallet'));
    expect(screen.queryByRole('alert')).toBeNull();
    fireEvent.click(screen.getByText('Sync wallet'));
    expect(screen.getByRole('alert').textContent).toBe(error);
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['skipped', 'Verify this wallet before syncing it.'],
    ['error', 'Some wallet balances could not be refreshed. Please try again later.'],
  ])('shows a %s result and clears it after a successful retry', async (status, error) => {
    api.post.mockResolvedValueOnce({ data: { success: false, wallet, syncResult: { status, error } } });
    render(
      <QueryClientProvider client={queryClient}>
        <WalletsPage />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByText('Sync wallet'));
    fireEvent.click(screen.getByRole('button', { name: 'Sync' }));
    expect((await screen.findByRole('alert')).textContent).toBe(error);
    api.post.mockResolvedValueOnce({ data: { success: true, wallet, syncResult: { status: 'success' } } });
    fireEvent.click(screen.getByRole('button', { name: 'Sync' }));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(api.post).toHaveBeenCalledTimes(2);
  });
});
