import React from 'react';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Wallet } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';
import { useTransfers } from './useTransfers';

jest.mock('../../services/apiClient', () => ({ apiClient: { get: jest.fn(), post: jest.fn() } }));
jest.mock('../../hooks/useUserPreferences', () => ({
  useUserPreferences: () => ({ selectedAccount: { uuid: 'owner' } }),
}));
jest.mock('../../_mock/mockDataEnabled', () => ({ mockDataEnabled: () => false }));

const wallet = {
  uuid: 'wallet-base',
  address: `0x${'a'.repeat(40)}`,
  chain: 'base',
  nativeBalance: '1',
  nativeMarketValue: '1',
  verificationStatus: 'VERIFIED',
} as Wallet;
const contract = `0x${'2'.repeat(40)}`;
let client: QueryClient;
let active: boolean;
let holdingWallet: string;
function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
beforeEach(() => {
  active = true;
  holdingWallet = wallet.uuid;
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false, gcTime: 0 } },
  });
  (apiClient.get as jest.Mock).mockImplementation(async (url: string) => ({
    data: url.includes('/holdings/')
      ? [
          {
            uuid: 'token-holding',
            walletUuid: holdingWallet,
            chain: 'base',
            quantity: '3',
            assetSymbol: 'MULTI',
            assetName: 'Multi-chain token',
            marketValue: '3',
            asset: {
              isActive: true,
              assetType: 'erc20_token',
              decimals: 18,
              contractAddress: `0x${'1'.repeat(40)}`,
              chainDeployments: [
                { chain: 'ethereum', contractAddress: `0x${'1'.repeat(40)}`, decimals: 18, isActive: true },
                { chain: 'base', contractAddress: contract, decimals: 0, isActive: active },
              ],
            },
          },
        ]
      : { results: [wallet], count: 1, next: null, previous: null },
  }));
});
afterEach(() => {
  client.clear();
});

describe('mobile token deployment selection', () => {
  it('offers the wallet network contract with its zero decimals', async () => {
    const { result } = await renderHook(() => useTransfers(), { wrapper });
    await act(async () => {
      result.current!.selectWallet(wallet);
    });
    await waitFor(() => expect(result.current!.isLoadingHoldings).toBe(false));
    expect(result.current!.transferableAssets.find((row) => row.uuid === 'token-holding')).toMatchObject({
      contractAddress: contract,
      decimals: 0,
    });
    expect(result.current!.transferableAssets.find((row) => row.isNative)).toMatchObject({
      symbol: 'ETH',
      chain: 'base',
    });
  });
  it.each(['disabled', 'different-wallet'])('does not offer a %s holding', async (reason) => {
    active = reason !== 'disabled';
    holdingWallet = reason === 'different-wallet' ? 'another-wallet' : wallet.uuid;
    const { result } = await renderHook(() => useTransfers(), { wrapper });
    await act(async () => {
      result.current!.selectWallet(wallet);
    });
    await waitFor(() => expect(result.current!.isLoadingHoldings).toBe(false));
    expect(result.current!.transferableAssets.some((row) => row.uuid === 'token-holding')).toBe(false);
  });
});
