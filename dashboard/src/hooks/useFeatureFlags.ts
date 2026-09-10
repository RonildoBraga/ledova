import { useQuery } from '@tanstack/react-query';
import { getFeatureFlags, readFeatureFlags, CACHE_TIMING } from '@ledova/shared';
import apiClient from '@services/apiClient';

export interface FeatureFlags {
  tradingEnabled: boolean;
  isLoading: boolean;
}

export function useFeatureFlags(): FeatureFlags {
  const query = useQuery({
    queryKey: ['featureFlags'],
    queryFn: () => getFeatureFlags(apiClient),
    staleTime: CACHE_TIMING.LONG_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const { isEnabled } = readFeatureFlags(query.data?.data?.results || []);

  return {
    tradingEnabled: isEnabled('trading_enabled'),
    isLoading: query.isLoading,
  };
}
