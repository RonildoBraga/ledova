import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCompanyTokens, getCompanyTokenHolders, createCompanyToken } from '@ledova/shared-services';
import type { TokenCreate, CompanyShareToken, TokenHoldersResponse } from '@ledova/shared-types';
import { apiClient } from '../services/apiClient';

type ShareholderSummary = {
  address: string;
  name: string | null;
  totalBalance: number;
  tokens: Array<{ name: string; symbol: string; balance: number; percentage: number }>;
};

export function useCompanyTokensList() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['company-tokens', page, statusFilter],
    queryFn: () =>
      getCompanyTokens(apiClient, {
        page,
        page_size: 10,
        ...(statusFilter ? { status: statusFilter } : {}),
      }),
  });

  const tokens = data?.data?.results || [];
  const totalCount = data?.data?.count || 0;
  const totalPages = Math.ceil(totalCount / 10);

  const createMutation = useMutation({
    mutationFn: (tokenData: TokenCreate) => createCompanyToken(apiClient, tokenData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-tokens'] });
      queryClient.invalidateQueries({ queryKey: ['company-stats'] });
    },
  });

  return {
    tokens,
    totalCount,
    page,
    totalPages,
    statusFilter,
    isLoading,
    error,
    setPage,
    setStatusFilter,
    refetch,
    createToken: createMutation.mutateAsync,
    isCreating: createMutation.isPending,
    createError: createMutation.error,
  };
}

export function useCompanyShareholders() {
  const { data: tokensData, isLoading: tokensLoading } = useQuery({
    queryKey: ['company-tokens-all'],
    queryFn: () => getCompanyTokens(apiClient, { page_size: 100 }),
  });

  const deployedTokens = (tokensData?.data?.results || []).filter((t: CompanyShareToken) => t.status === 'deployed');

  const holdersQuery = useQuery({
    queryKey: ['all-shareholders', deployedTokens.map((t: CompanyShareToken) => t.uuid)],
    queryFn: async () => {
      if (deployedTokens.length === 0) return [];

      const results = await Promise.all(
        deployedTokens.map(async (token: CompanyShareToken) => {
          try {
            const response = await getCompanyTokenHolders(apiClient, token.uuid);
            const data: TokenHoldersResponse = response.data;
            return { token, holders: data.holders };
          } catch {
            return { token, holders: [] };
          }
        }),
      );
      return results;
    },
    enabled: deployedTokens.length > 0,
  });

  const holdersMap = new Map<string, ShareholderSummary>();

  if (holdersQuery.data) {
    for (const { token, holders } of holdersQuery.data) {
      for (const holder of holders) {
        const existing: ShareholderSummary = holdersMap.get(holder.address) || {
          address: holder.address,
          name: holder.name,
          totalBalance: 0,
          tokens: [],
        };
        const balance = parseFloat(holder.balance);
        existing.totalBalance += balance;
        existing.tokens.push({
          name: token.name,
          symbol: token.symbol,
          balance,
          percentage: holder.percentage,
        });
        if (holder.name && !existing.name) existing.name = holder.name;
        holdersMap.set(holder.address, existing);
      }
    }
  }

  const holders = Array.from(holdersMap.values()).sort((a, b) => b.totalBalance - a.totalBalance);

  return {
    holders,
    deployedTokens,
    isLoading: tokensLoading || holdersQuery.isLoading,
    refetch: async () => {
      await holdersQuery.refetch();
    },
  };
}
