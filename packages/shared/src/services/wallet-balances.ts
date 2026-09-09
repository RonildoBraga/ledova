import { AxiosInstance } from 'axios';
import { getChainName, WALLET_ENDPOINTS } from '../constants';
import type { WalletHolding, BatchBalanceResponse } from '../types';

export const getWalletHoldings = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<WalletHolding[]>(WALLET_ENDPOINTS.HOLDINGS(uuid));

export const fetchBatchBalances = async (
  apiClient: AxiosInstance,
  addresses: string[],
  chain: 'ETH' | 'BTC' = 'ETH',
): Promise<BatchBalanceResponse> => {
  if (addresses.length > 20) {
    throw new Error('Maximum 20 addresses allowed per request');
  }

  const response = await apiClient.post<BatchBalanceResponse>(WALLET_ENDPOINTS.BATCH_BALANCES, {
    addresses,
    chain: getChainName(chain),
  });

  return response.data;
};
