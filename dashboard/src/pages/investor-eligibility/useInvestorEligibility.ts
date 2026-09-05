import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CACHE_TIMING, getInvestorClassifications, getInvestorEligibility } from '@ledova/shared';
import apiClient from '@services/apiClient';

export function useInvestorEligibility() {
  const queryClient = useQueryClient();

  const eligibilityQuery = useQuery({
    queryKey: ['investor-eligibility'],
    queryFn: () => getInvestorEligibility(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const classificationsQuery = useQuery({
    queryKey: ['investor-classifications'],
    queryFn: () => getInvestorClassifications(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['investor-eligibility'] });
    queryClient.invalidateQueries({ queryKey: ['investor-classifications'] });
  };

  return {
    eligibility: eligibilityQuery.data?.data,
    classifications: classificationsQuery.data?.data?.results ?? [],
    isLoading: eligibilityQuery.isLoading || classificationsQuery.isLoading,
    refresh,
  };
}
