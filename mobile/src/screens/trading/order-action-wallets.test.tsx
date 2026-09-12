import React from 'react';
import { cleanup, renderHook, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BLOCKCHAIN, WALLET_ENDPOINTS, type Wallet } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';
import { useUserTradingWallets } from './useTrading';
import { accountUuid, response, wallet } from '../../../../packages/shared/tests/fixtures/order-submissions';
jest.mock('../../services/apiClient', () => ({ apiClient: jest.requireActual('axios').default.create() }));
jest.mock('../../hooks/useUserPreferences', () => ({
  useUserPreferences: () => ({ selectedAccount: { uuid: '20000000-0000-4000-8000-000000000001' }, isLoading: false }),
}));
let client: QueryClient;
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
});
afterEach(async () => {
  await cleanup();
  client.clear();
});
it('retains unverified EVM action wallets and the existing verified-only create pool from the same scoped response', async () => {
  const verified = { ...wallet, verificationStatus: 'VERIFIED', chain: BLOCKCHAIN.ETHEREUM } as Wallet;
  const unverified = {
    ...wallet,
    uuid: '30000000-0000-4000-8000-000000000009',
    verificationStatus: 'PENDING',
    chain: BLOCKCHAIN.BASE,
  } as Wallet;
  const bitcoin = {
    ...wallet,
    uuid: '30000000-0000-4000-8000-000000000008',
    verificationStatus: 'VERIFIED',
    chain: BLOCKCHAIN.BITCOIN,
  } as Wallet;
  const calls: unknown[] = [];
  apiClient.defaults.adapter = async (config) => {
    calls.push([config.method, config.url, config.params]);
    return response(
      config,
      JSON.stringify({ count: 3, next: null, previous: null, results: [verified, unverified, bitcoin] }),
    );
  };
  const view = await renderHook(() => useUserTradingWallets(), {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
  await waitFor(() => expect(view.result.current.actionWallets).toEqual([verified, unverified]));
  expect(view.result.current.wallets).toEqual([verified]);
  expect(view.result.current.walletAddresses).toEqual([verified.address]);
  expect(calls).toEqual([['get', WALLET_ENDPOINTS.BASE, { user_account: accountUuid }]]);
});
