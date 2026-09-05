import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getCompanyToken,
  getCompanyTokenHolders,
  getCompanyTokenIssuances,
  getCapitalIncreases,
  issueCompanyShares,
} from '@ledova/shared';
import type { CompanyShareToken, TokenHolder, TokenIssuance, CapitalIncreaseRequest } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';

export function useTokenDetail(uuid: string) {
  const queryClient = useQueryClient();

  const tokenQuery = useQuery<CompanyShareToken>({
    queryKey: ['company-token', uuid],
    queryFn: () => getCompanyToken(apiClient, uuid).then((res) => res.data),
    enabled: !!uuid,
  });

  const holdersQuery = useQuery({
    queryKey: ['company-token-holders', uuid],
    queryFn: () => getCompanyTokenHolders(apiClient, uuid).then((res) => res.data),
    enabled: !!uuid && tokenQuery.data?.status === 'deployed',
  });

  const issuancesQuery = useQuery({
    queryKey: ['company-token-issuances', uuid],
    queryFn: () => getCompanyTokenIssuances(apiClient, uuid).then((res) => res.data),
    enabled: !!uuid,
  });

  const capitalIncreasesQuery = useQuery({
    queryKey: ['company-token-capital-increases', uuid],
    queryFn: () => getCapitalIncreases(apiClient, { token: uuid }).then((res) => res.data),
    enabled: !!uuid && tokenQuery.data?.status === 'deployed',
  });

  const holders: TokenHolder[] = holdersQuery.data?.holders || [];
  const totalHolders = holdersQuery.data?.totalHolders || 0;
  const issuances: TokenIssuance[] = issuancesQuery.data?.results || [];
  const issuanceCount = issuancesQuery.data?.count || 0;
  const capitalIncreases: CapitalIncreaseRequest[] = capitalIncreasesQuery.data?.results || [];
  const capitalIncreaseCount = capitalIncreasesQuery.data?.count || 0;

  const issueMutation = useMutation({
    mutationFn: (data: { recipient: string; amount: number; reason?: string }) =>
      issueCompanyShares(apiClient, uuid, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-token-issuances', uuid] });
      queryClient.invalidateQueries({ queryKey: ['company-token-holders', uuid] });
    },
  });

  return {
    token: tokenQuery.data || null,
    isLoading: tokenQuery.isLoading,
    error: tokenQuery.error,
    holders,
    totalHolders,
    isLoadingHolders: holdersQuery.isLoading,
    issuances,
    issuanceCount,
    isLoadingIssuances: issuancesQuery.isLoading,
    capitalIncreases,
    capitalIncreaseCount,
    isLoadingCapitalIncreases: capitalIncreasesQuery.isLoading,
    issueShares: issueMutation.mutateAsync,
    isIssuing: issueMutation.isPending,
    issueError: issueMutation.error,
    resetIssueError: issueMutation.reset,
    refetch: async () => {
      await Promise.all([
        tokenQuery.refetch(),
        holdersQuery.refetch(),
        issuancesQuery.refetch(),
        capitalIncreasesQuery.refetch(),
      ]);
    },
  };
}
