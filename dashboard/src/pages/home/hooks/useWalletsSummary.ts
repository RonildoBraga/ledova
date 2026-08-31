import { useQuery } from '@tanstack/react-query';
import { getWallets } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import apiClient from '@services/apiClient';

export function useWalletsSummary(accountUuid: string | undefined) {
  const walletsQuery = useQuery({
    queryKey: ['home-wallets', accountUuid],
    queryFn: () => getWallets(apiClient, { user_account: accountUuid! }),
    enabled: !!accountUuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  return {
    walletsList: walletsQuery.data?.data?.results || [],
    isLoading: walletsQuery.isLoading,
  };
}
