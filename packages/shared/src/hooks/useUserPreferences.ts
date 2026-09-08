import { useQuery } from '@tanstack/react-query';

import { CACHE_TIMING } from '../constants/api';
import { getCurrentUserPreferences } from '../services/userPreferences';
import { useApiClient } from './useApiClient';
import { useAuth } from './useAuth';

export const USER_PREFERENCES_QUERY_KEY = ['userPreferences'] as const;

export function useUserPreferences() {
  const apiClient = useApiClient();
  const { isAuthenticated } = useAuth();
  const query = useQuery({
    queryKey: USER_PREFERENCES_QUERY_KEY,
    queryFn: () => getCurrentUserPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });
  const preferences = isAuthenticated ? query.data?.data : undefined;

  return {
    preferences,
    selectedPortfolio: preferences?.selectedPortfolio ?? null,
    selectedAccount: preferences?.selectedAccount ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}
