import { AxiosInstance } from 'axios';
import { getChainName, WALLET_ENDPOINTS } from '../constants';
import type { WalletHolding, BatchBalanceResponse, WalletPreviewChain, DerivedAddress } from '../types';
import { importAddressKey } from '../utils/wallet-import';

export const getWalletHoldings = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<WalletHolding[]>(WALLET_ENDPOINTS.HOLDINGS(uuid));

export const fetchBatchBalances = async (
  apiClient: AxiosInstance,
  { addresses, chain, userAccount }: { addresses: string[]; chain: WalletPreviewChain; userAccount: string },
): Promise<BatchBalanceResponse> => {
  if (!userAccount || !['ethereum', 'base', 'bitcoin'].includes(chain) || !addresses.length || addresses.length > 20) {
    throw new Error('Select an account, network and between 1 and 20 addresses');
  }

  const response = await apiClient.post<BatchBalanceResponse>(WALLET_ENDPOINTS.BATCH_BALANCES, {
    addresses,
    chain,
    userAccount,
  });

  if (response.data.userAccount !== userAccount || response.data.chain !== chain) {
    throw new Error('Balance response does not match the selected account and network');
  }
  return response.data;
};

export async function fetchImportBalances(
  apiClient: AxiosInstance,
  addresses: DerivedAddress[],
  userAccount: string | undefined,
): Promise<Map<string, string>> {
  const balances = new Map(addresses.map((address) => [importAddressKey(address), 'Unavailable']));
  if (!userAccount) return balances;
  const chains: WalletPreviewChain[] = ['ethereum', 'base', 'bitcoin'];
  await Promise.all(
    chains.map(async (chain) => {
      const group = addresses.filter((address) => getChainName(address.networkType) === chain);
      for (let offset = 0; offset < group.length; offset += 20) {
        const batch = group.slice(offset, offset + 20);
        try {
          const response = await fetchBatchBalances(apiClient, {
            userAccount,
            chain,
            addresses: batch.map((item) => item.address),
          });
          for (const address of batch) {
            const balance = response.balances[address.address];
            if (balance != null)
              balances.set(importAddressKey(address), `${balance} ${chain === 'bitcoin' ? 'BTC' : 'ETH'}`);
          }
        } catch {}
      }
    }),
  );
  return balances;
}
