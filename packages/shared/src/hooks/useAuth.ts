import { useQuery } from '@tanstack/react-query';

import { CACHE_TIMING } from '../constants/api';
import { verifyAuth } from '../services/auth';
import { useApiClient } from './useApiClient';

export const AUTH_QUERY_KEY = ['auth', 'verify'] as const;

export function useAuth() {
  const apiClient = useApiClient();
  const query = useQuery({
    queryKey: AUTH_QUERY_KEY,
    queryFn: () => verifyAuth(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    retry: false,
  });

  return {
    isAuthenticated: query.isSuccess && (query.data?.data?.valid ?? false),
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    refetch: query.refetch,
  };
}
