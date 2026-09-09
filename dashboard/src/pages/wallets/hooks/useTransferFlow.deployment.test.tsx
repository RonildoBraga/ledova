// @vitest-environment jsdom

import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Wallet } from '@ledova/shared';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@services/apiClient', () => ({ default: api }));
vi.mock('./useCryptoTransferSigning', () => ({ useCryptoTransferSigning: () => ({ reset: vi.fn() }) }));

import { useTransferFlow } from './useTransferFlow';

const wallet = {
  uuid: 'wallet-base',
  address: `0x${'a'.repeat(40)}`,
  chain: 'base',
  nativeBalance: '1',
  nativeMarketValue: '1',
} as Wallet;
const contract = `0x${'2'.repeat(40)}`;
let client: QueryClient;
function holding(active = true) {
  return {
    uuid: 'token-holding',
    walletUuid: wallet.uuid,
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
  };
}
function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  api.get.mockImplementation(async (url: string) => ({
    data: url.includes('/holdings/') ? [holding()] : { isWhitelisted: true },
  }));
});
afterEach(() => {
  cleanup();
  client.clear();
});

describe('dashboard token deployment selection', () => {
  it('offers the wallet network contract with its zero decimals', async () => {
    const { result } = renderHook(() => useTransferFlow(wallet), { wrapper });
    await waitFor(() => expect(result.current.isLoadingAssets).toBe(false));
    expect(result.current.assets.find((row) => row.id === 'token-holding')).toMatchObject({
      tokenAddress: contract,
      decimals: 0,
      displayBalance: '3',
    });
  });
  it('does not offer the other networks contract when this deployment is disabled', async () => {
    api.get.mockResolvedValue({ data: [holding(false)] });
    const { result } = renderHook(() => useTransferFlow(wallet), { wrapper });
    await waitFor(() => expect(result.current.isLoadingAssets).toBe(false));
    expect(result.current.assets.some((row) => row.id === 'token-holding')).toBe(false);
  });
  it('does not reuse a holding returned for a different wallet', async () => {
    const { result } = renderHook(() => useTransferFlow({ ...wallet, uuid: 'different-wallet' }), { wrapper });
    await waitFor(() => expect(result.current.isLoadingAssets).toBe(false));
    expect(result.current.assets.some((row) => row.id === 'token-holding')).toBe(false);
  });
});
