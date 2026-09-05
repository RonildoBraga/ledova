import { useQuery } from '@tanstack/react-query';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { getFeatureFlags, CACHE_TIMING } from '@ledova/shared';
import type { FeatureFlag } from '@ledova/shared';
import { apiClient } from '../services/apiClient';

function isVersionAtLeast(current: string, minimum: string): boolean {
  const currentParts = current.split('.').map(Number);
  const minimumParts = minimum.split('.').map(Number);

  for (let i = 0; i < 3; i++) {
    const cur = currentParts[i] || 0;
    const min = minimumParts[i] || 0;
    if (cur > min) return true;
    if (cur < min) return false;
  }
  return true;
}

function filterFlagForPlatform(flag: FeatureFlag): boolean {
  const platform = Platform.OS;

  switch (flag.platform) {
    case 'all':
    case 'mobile':
      return true;
    case 'ios':
      return platform === 'ios';
    case 'android':
      return platform === 'android';
    case 'web':
      return false;
    default:
      return false;
  }
}

function filterFlagForVersion(flag: FeatureFlag): boolean {
  if (!flag.minAppVersion) return true;

  const appVersion = Constants.expoConfig?.version;
  if (!appVersion) return true;

  return isVersionAtLeast(appVersion, flag.minAppVersion);
}

export function useFeatureFlags() {
  const query = useQuery({
    queryKey: ['featureFlags'],
    queryFn: () => getFeatureFlags(apiClient),
    staleTime: CACHE_TIMING.LONG_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    refetchOnWindowFocus: false,
    refetchOnReconnect: true,
  });

  const allFlags: FeatureFlag[] = query.data?.data?.results || [];
  const flags = allFlags.filter((flag: FeatureFlag) => filterFlagForPlatform(flag) && filterFlagForVersion(flag));

  const isEnabled = (name: string): boolean => flags.some((flag: FeatureFlag) => flag.name === name);

  return {
    flags,
    isEnabled,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}
