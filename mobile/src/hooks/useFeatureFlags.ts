import { useQuery } from '@tanstack/react-query';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { getFeatureFlags, readFeatureFlags, CACHE_TIMING } from '@ledova/shared';
import { apiClient } from '../services/apiClient';

export function useFeatureFlags() {
  const query = useQuery({
    queryKey: ['featureFlags'],
    queryFn: () => getFeatureFlags(apiClient),
    staleTime: CACHE_TIMING.LONG_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    refetchOnWindowFocus: false,
    refetchOnReconnect: true,
  });

  const { flags, isEnabled } = readFeatureFlags(query.data?.data?.results || [], {
    mobilePlatform: Platform.OS,
    get appVersion() {
      return Constants.expoConfig?.version;
    },
  });

  return {
    flags,
    isEnabled,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}
