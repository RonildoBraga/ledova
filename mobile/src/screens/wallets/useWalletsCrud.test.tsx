import React from 'react';
import { Alert } from 'react-native';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { apiClient } from '../../services/apiClient';
import { useWalletsCrud } from './useWalletsCrud';

jest.mock('../../services/apiClient', () => ({ apiClient: { get: jest.fn(), post: jest.fn() } }));
jest.mock('../../hooks/useUserPreferences', () => ({
  useUserPreferences: () => ({ selectedAccount: { uuid: 'owner' } }),
}));
jest.mock('../../_mock/mockDataEnabled', () => ({ mockDataEnabled: () => false }));

let client: QueryClient;
const post = apiClient.post as jest.Mock;

beforeEach(() => {
  post.mockReset();
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 } },
  });
  (apiClient.get as jest.Mock).mockResolvedValue({ data: { results: [], count: 0, next: null, previous: null } });
  jest.spyOn(Alert, 'alert').mockImplementation(() => {});
});

afterEach(() => {
  client.clear();
});

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('wallet sync feedback through the shared service', () => {
  it.each([
    ['skipped', 'Verify this wallet before syncing it.'],
    ['error', 'Wallet sync could not finish. Please try again later.'],
  ])('announces a %s result and ends the spinner', async (status, error) => {
    post.mockResolvedValue({ data: { success: false, syncResult: { status, error } } });
    const { result } = await renderHook(() => useWalletsCrud(), { wrapper });
    await waitFor(() => expect(result.current?.isLoading).toBe(false));
    await act(async () => {
      await expect(result.current!.syncWallet('wallet-1')).rejects.toMatchObject({ message: error });
    });
    await waitFor(() => expect(Alert.alert).toHaveBeenCalledWith('Wallet not synced', error));
    expect(result.current?.isSyncing).toBe(false);
    expect(result.current?.syncingWalletIds.size).toBe(0);
  });

  it('refreshes a successful sync without an error alert', async () => {
    post.mockResolvedValue({ data: { success: true, syncResult: { status: 'success' } } });
    const { result } = await renderHook(() => useWalletsCrud(), { wrapper });
    await waitFor(() => expect(result.current?.isLoading).toBe(false));
    await act(async () => {
      await result.current!.syncWallet('wallet-1');
    });
    expect(Alert.alert).not.toHaveBeenCalled();
  });

  it('tracks concurrent wallets independently and reuses an already pending request', async () => {
    let finishFirst!: (response: unknown) => void;
    let finishSecond!: (response: unknown) => void;
    const firstResponse = new Promise((resolve) => {
      finishFirst = resolve;
    });
    const secondResponse = new Promise((resolve) => {
      finishSecond = resolve;
    });
    post.mockImplementation((url: string) => (url.includes('wallet-1') ? firstResponse : secondResponse));
    const { result } = await renderHook(() => useWalletsCrud(), { wrapper });
    await waitFor(() => expect(result.current?.isLoading).toBe(false));
    let first!: Promise<unknown>;
    let duplicate!: Promise<unknown>;
    let second!: Promise<unknown>;
    await act(async () => {
      first = result.current!.syncWallet('wallet-1');
      second = result.current!.syncWallet('wallet-2');
      duplicate = result.current!.syncWallet('wallet-1');
    });
    try {
      expect(duplicate).toBe(first);
      expect(post).toHaveBeenCalledTimes(2);
      expect(result.current?.syncingWalletIds).toEqual(new Set(['wallet-1', 'wallet-2']));
      await act(async () => {
        finishFirst({ data: { success: true, syncResult: { status: 'success' } } });
        await first;
      });
      expect(result.current?.syncingWalletIds).toEqual(new Set(['wallet-2']));
      expect(result.current?.isSyncing).toBe(true);
      const error = 'Wallet sync could not finish. Please try again later.';
      await act(async () => {
        const rejected = expect(second).rejects.toMatchObject({ message: error });
        finishSecond({ data: { success: false, syncResult: { status: 'error', error } } });
        await rejected;
      });
      expect(Alert.alert).toHaveBeenCalledTimes(1);
      expect(Alert.alert).toHaveBeenCalledWith('Wallet not synced', error);
      expect(result.current?.syncingWalletIds.size).toBe(0);
      expect(result.current?.isSyncing).toBe(false);
    } finally {
      await act(async () => {
        finishFirst({ data: { success: true, syncResult: { status: 'success' } } });
        finishSecond({ data: { success: true, syncResult: { status: 'success' } } });
        await Promise.allSettled([first, duplicate, second]);
      });
    }
  });
});
