import { AxiosInstance } from 'axios';
import { getChainName } from '@ledova/shared-constants';
import type { WalletHolding, PaginatedResponse, BatchBalanceResponse } from '@ledova/shared-types';

export interface WalletHoldingsQueryParams {
  include_asset?: boolean;
}

export const getWalletHoldings = (apiClient: AxiosInstance, uuid: string, params?: WalletHoldingsQueryParams) =>
  apiClient.get<PaginatedResponse<WalletHolding>>(`/api/wallets/${uuid}/holdings/`, { params });

export const fetchBatchBalances = async (
  apiClient: AxiosInstance,
  addresses: string[],
  chain: 'ETH' | 'BTC' = 'ETH',
): Promise<BatchBalanceResponse> => {
  if (addresses.length > 20) {
    throw new Error('Maximum 20 addresses allowed per request');
  }

  const response = await apiClient.post<BatchBalanceResponse>('/api/wallets/batch-check-balances/', {
    addresses,
    chain: getChainName(chain),
  });

  return response.data;
};
