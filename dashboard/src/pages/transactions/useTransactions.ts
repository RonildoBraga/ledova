import { useState, useCallback } from 'react';
import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import { CACHE_TIMING, getTransactions, getTransactionsNextPage, getWallets } from '@ledova/shared';
import type { TransactionQueryParams } from '@ledova/shared';
import apiClient from '@services/apiClient';

export interface TransactionFilters {
  wallet?: string;
  direction?: 'incoming' | 'outgoing';
  chain?: string;
  min_amount?: number;
  max_amount?: number;
  start_date?: string;
  end_date?: string;
}

export function useTransactions() {
  const [filters, setFilters] = useState<TransactionFilters>({});
  const [appliedFilters, setAppliedFilters] = useState<TransactionFilters>({});

  const { data: walletsResponse } = useQuery({
    queryKey: ['wallets'],
    queryFn: () => getWallets(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });

  const wallets = walletsResponse?.data?.results || [];

  const {
    data: ledovaData,
    isLoading,
    isFetchingNextPage: isLoadingMore,
    hasNextPage: hasLedovaNextPage,
    fetchNextPage: fetchLedovaNextPage,
  } = useInfiniteQuery({
    queryKey: ['transactions', appliedFilters],
    queryFn: ({ pageParam = 1 }) =>
      getTransactions(apiClient, { ...appliedFilters, page: pageParam } as TransactionQueryParams),
    getNextPageParam: getTransactionsNextPage,
    initialPageParam: 1,
    enabled: wallets.length > 0,
    staleTime: CACHE_TIMING.VERY_SHORT_STALE_TIME,
    gcTime: CACHE_TIMING.MEDIUM_GC_TIME,
  });

  const transactions = ledovaData?.pages.flatMap((page) => page.data?.results || []) || [];
  const totalCount = ledovaData?.pages[0]?.data?.count || 0;
  const hasNextPage = hasLedovaNextPage ?? false;

  const hasActiveFilters = Object.keys(appliedFilters).some(
    (key) => key !== 'page' && key !== 'page_size' && appliedFilters[key as keyof TransactionFilters] !== undefined,
  );

  const loadMore = useCallback(() => {
    if (hasLedovaNextPage && !isLoadingMore) {
      fetchLedovaNextPage();
    }
  }, [hasLedovaNextPage, isLoadingMore, fetchLedovaNextPage]);

  const applyFilters = () => setAppliedFilters(filters);

  const updateAndApplyFilters = (newFilters: TransactionFilters) => {
    setFilters(newFilters);
    setAppliedFilters(newFilters);
  };

  const clearFilters = () => {
    setFilters({});
    setAppliedFilters({});
  };

  return {
    transactions,
    wallets,
    isLoading,
    isLoadingMore,
    filters,
    hasActiveFilters,
    totalCount,
    hasNextPage,
    applyFilters,
    updateFilters: setFilters,
    updateAndApplyFilters,
    clearFilters,
    loadMore,
  };
}
