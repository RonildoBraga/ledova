import { useQuery } from '@tanstack/react-query';
import { verifyAuth } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import apiClient from '@services/apiClient';

export const AUTH_QUERY_KEY = ['auth', 'verify'] as const;

export const useAuth = () => {
  const query = useQuery({
    queryKey: AUTH_QUERY_KEY,
    queryFn: () => verifyAuth(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    retry: false,
    retryOnMount: false,
    refetchOnWindowFocus: true,
  });

  return {
    isAuthenticated: query.isSuccess && (query.data?.data?.valid ?? false),
    isLoading: query.isLoading,
    refetch: query.refetch,
  };
};
