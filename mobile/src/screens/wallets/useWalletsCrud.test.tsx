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
    expect(result.current?.syncingWalletId).toBeUndefined();
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
});
