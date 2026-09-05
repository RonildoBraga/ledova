import { useQuery } from '@tanstack/react-query';
import { getCurrentUserPreferences, CACHE_TIMING } from '@ledova/shared';
import { apiClient } from '../services/apiClient';
import { useAuth } from './useAuth';

export function useUserPreferences() {
  const { isAuthenticated } = useAuth();

  const preferencesQuery = useQuery({
    queryKey: ['userPreferences'],
    queryFn: () => getCurrentUserPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const preferences = preferencesQuery.data?.data;

  return {
    preferences,

    selectedPortfolio: preferences?.selectedPortfolio ?? null,
    selectedAccount: preferences?.selectedAccount ?? null,

    isLoading: preferencesQuery.isLoading,
    isError: preferencesQuery.isError,
    error: preferencesQuery.error,

    refetch: preferencesQuery.refetch,
  };
}
