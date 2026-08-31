import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getUserProfiles, getPortfolios, getCurrentUserPreferences } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import { apiClient } from '../../services/apiClient';
import { useAuth } from '../../hooks/useAuth';

export const useUserProfile = () => {
  const { isAuthenticated } = useAuth();

  const userProfileQuery = useQuery({
    queryKey: ['userProfiles'],
    queryFn: () => getUserProfiles(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const portfoliosQuery = useQuery({
    queryKey: ['portfolios'],
    queryFn: () => getPortfolios(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const preferencesQuery = useQuery({
    queryKey: ['userPreferences'],
    queryFn: () => getCurrentUserPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    retry: (failureCount, error: unknown) => {
      if (
        error &&
        typeof error === 'object' &&
        'response' in error &&
        error.response &&
        typeof error.response === 'object' &&
        'status' in error.response &&
        error.response.status === 404
      ) {
        return false;
      }
      return failureCount < 3;
    },
  });

  const userProfile = useMemo(
    () => userProfileQuery.data?.data?.results?.[0] || null,
    [userProfileQuery.data?.data?.results],
  );

  const isLoading = useMemo(
    () => userProfileQuery.isLoading || portfoliosQuery.isLoading,
    [userProfileQuery.isLoading, portfoliosQuery.isLoading],
  );

  const isError = useMemo(
    () => userProfileQuery.isError || portfoliosQuery.isError,
    [userProfileQuery.isError, portfoliosQuery.isError],
  );

  const refreshProfile = () => {
    userProfileQuery.refetch();
    portfoliosQuery.refetch();
    preferencesQuery.refetch();
  };

  return {
    userProfile,
    isLoading,
    isError,
    refreshProfile,
  };
};
