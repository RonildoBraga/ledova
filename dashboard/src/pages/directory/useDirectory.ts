import { useQuery } from '@tanstack/react-query';
import {
  CACHE_TIMING,
  getDirectoryToken,
  getDirectoryTokens,
  getInvestorEligibility,
  getOperator,
} from '@ledova/shared';
import apiClient from '@services/apiClient';

export function useDirectoryTokens() {
  const eligibility = useQuery({
    queryKey: ['investor-eligibility'],
    queryFn: () => getInvestorEligibility(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const tokens = useQuery({
    queryKey: ['directory', 'tokens'],
    queryFn: () => getDirectoryTokens(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  return {
    tokens: tokens.data?.data?.results ?? [],
    isEligible: eligibility.data?.data?.isEligible ?? false,
    isLoading: tokens.isLoading || eligibility.isLoading,
  };
}

export function useDirectoryToken(uuid: string | undefined) {
  const token = useQuery({
    queryKey: ['directory', 'tokens', uuid],
    queryFn: () => getDirectoryToken(apiClient, uuid!),
    enabled: !!uuid,
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const operator = useQuery({
    queryKey: ['operator'],
    queryFn: () => getOperator(apiClient),
    enabled: token.isSuccess,
    staleTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  return {
    token: token.data?.data ?? null,
    operator: operator.data?.data ?? null,
    isLoading: token.isLoading || operator.isLoading,
    notFound: token.isError,
  };
}
