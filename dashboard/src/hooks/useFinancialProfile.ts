import { useQuery } from '@tanstack/react-query';
import { getFinancialProfiles } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import apiClient from '@services/apiClient';

export function useFinancialProfile() {
  const query = useQuery({
    queryKey: ['financialProfiles'],
    queryFn: () => getFinancialProfiles(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  return {
    financialProfile: query.data?.data?.results?.[0] || null,
    isLoading: query.isLoading,
    error: query.error,
  };
}
