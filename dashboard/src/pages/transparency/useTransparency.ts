import { useQuery } from '@tanstack/react-query';
import { CACHE_TIMING } from '@ledova/shared-constants';
import type { PaginatedResponse } from '@ledova/shared-types';
import apiClient from '@services/apiClient';

interface StablecoinListItem {
  uuid: string;
  symbol: string;
}

export interface ChainDeployment {
  chain: string;
  contractAddress: string;
  decimals: number;
  supply: string | null;
}

export interface StablecoinTransparency {
  uuid: string;
  name: string;
  symbol: string;
  decimals: number;
  totalSupply: string | null;
  reserveAmount: string | null;
  reserveUpdatedAt: string | null;
  chainDeployments: ChainDeployment[];
}

export function useTransparency() {
  const stablecoinsQuery = useQuery({
    queryKey: ['stablecoins'],
    queryFn: () => apiClient.get<PaginatedResponse<StablecoinListItem>>('/api/v1/trading/stablecoins/'),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.LONG_GC_TIME,
  });

  const audyUuid = stablecoinsQuery.data?.data?.results?.find((s) => s.symbol === 'AUDY')?.uuid;

  const transparencyQuery = useQuery({
    queryKey: ['stablecoin-transparency', audyUuid],
    queryFn: () => apiClient.get<StablecoinTransparency>(`/api/v1/trading/stablecoins/${audyUuid}/transparency/`),
    enabled: !!audyUuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.LONG_GC_TIME,
  });

  return {
    data: transparencyQuery.data?.data || null,
    isLoading: stablecoinsQuery.isLoading || transparencyQuery.isLoading,
    isError: stablecoinsQuery.isError || transparencyQuery.isError,
  };
}
