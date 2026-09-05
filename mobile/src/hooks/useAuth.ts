import { useQuery } from '@tanstack/react-query';
import { verifyAuth, CACHE_TIMING } from '@ledova/shared';
import { apiClient } from '../services/apiClient';

export const useAuth = () => {
  const query = useQuery({
    queryKey: ['auth', 'verify'],
    queryFn: () => verifyAuth(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    retry: false,
    refetchOnWindowFocus: false, // Mobile doesn't have window focus
    refetchOnReconnect: true, // But should refetch on network reconnect
  });

  return {
    isAuthenticated: query.isSuccess && (query.data?.data?.valid ?? false),
    refetch: query.refetch,
  };
};
