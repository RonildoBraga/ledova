import { useQuery } from '@tanstack/react-query';
import { getFeatureFlags, CACHE_TIMING } from '@ledova/shared';
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

  const flags = query.data?.data?.results || [];
  const isEnabled = (name: string) => flags.some((flag) => flag.name === name && flag.enabled);

  return {
    tradingEnabled: isEnabled('trading_enabled'),
    isLoading: query.isLoading,
  };
}
