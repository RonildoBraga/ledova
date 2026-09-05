import { useState, useCallback, useMemo } from 'react';
import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import { CACHE_TIMING, BLOCKCHAIN, getTransactions, getTransactionsNextPage, getWallets } from '@ledova/shared';
import type { TransactionQueryParams, Transaction, PaginatedResponse, Wallet } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';
import { generateMockTransactionsData } from './_mock/mock';
import { useMockData } from '../../_mock/useMockData';

export type { TransactionQueryParams };

interface MockPage {
  data: PaginatedResponse<Transaction>;
}

export function useTransactions() {
  const USE_MOCK_DATA = useMockData();
  const [filters, setFilters] = useState<TransactionQueryParams>({});
  const [appliedFilters, setAppliedFilters] = useState<TransactionQueryParams>({});
  const [currentMockPage, setCurrentMockPage] = useState(1);

  const { data: walletsResponse } = useQuery({
    queryKey: ['wallets'],
    queryFn: () => getWallets(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    enabled: !USE_MOCK_DATA,
  });

  const wallets: Wallet[] = walletsResponse?.data?.results || [];

  const ethWallets = useMemo(() => wallets.filter((w) => w.chain === BLOCKCHAIN.ETHEREUM), [wallets]);
  const btcWallets = useMemo(() => wallets.filter((w) => w.chain === BLOCKCHAIN.BITCOIN), [wallets]);
  const baseWallets = useMemo(() => wallets.filter((w) => w.chain === BLOCKCHAIN.BASE), [wallets]);

  const {
    data: transactionsData,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ['all-transactions', appliedFilters],
    queryFn: ({ pageParam = 1 }) => getTransactions(apiClient, { ...appliedFilters, page: pageParam }),
    getNextPageParam: getTransactionsNextPage,
    initialPageParam: 1,
    enabled: !USE_MOCK_DATA,
    staleTime: CACHE_TIMING.VERY_SHORT_STALE_TIME,
    gcTime: CACHE_TIMING.MEDIUM_GC_TIME,
  });

  const loadMore = useCallback(() => {
    if (!USE_MOCK_DATA && hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [USE_MOCK_DATA, hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (USE_MOCK_DATA) {
    const mockPages: MockPage[] = [];
    for (let i = 1; i <= currentMockPage; i++) {
      const pageData = generateMockTransactionsData(20, i);
      mockPages.push({
        data: {
          results: pageData.results,
          count: pageData.count,
          next: pageData.next,
          previous: pageData.previous,
        },
      });
    }

    const mockTransactions = mockPages.flatMap((page) => page.data?.results || []);
    const mockTotalCount = mockPages[0]?.data?.count || 0;
    const mockHasNextPage = mockPages[mockPages.length - 1]?.data?.next !== null;

    const mockLoadMore = () => {
      if (mockHasNextPage) {
        setCurrentMockPage((prev) => prev + 1);
      }
    };

    const hasActiveFilters = Object.keys(appliedFilters).some(
      (key) =>
        key !== 'page' && key !== 'page_size' && appliedFilters[key as keyof TransactionQueryParams] !== undefined,
    );

    return {
      transactions: mockTransactions,
      wallets: [],
      ethWallets: [],
      btcWallets: [],
      baseWallets: [],
      isLoading: false,
      isLoadingMore: false,
      filters,
      hasActiveFilters,
      totalCount: mockTotalCount,
      hasNextPage: mockHasNextPage,
      updateFilters: (newFilters: TransactionQueryParams) => setFilters(newFilters),
      applyFilters: () => setAppliedFilters(filters),
      updateAndApplyFilters: (newFilters: TransactionQueryParams) => {
        setFilters(newFilters);
        setAppliedFilters(newFilters);
      },
      clearFilters: () => {
        setFilters({});
        setAppliedFilters({});
      },
      loadMore: mockLoadMore,
      refetch: async () => ({ data: undefined }),
    };
  }

  const transactions = transactionsData?.pages.flatMap((page) => page.data?.results || []) || [];
  const totalCount = transactionsData?.pages[0]?.data?.count || 0;

  const hasActiveFilters = Object.keys(appliedFilters).some(
    (key) => key !== 'page' && key !== 'page_size' && appliedFilters[key as keyof TransactionQueryParams] !== undefined,
  );

  const updateFilters = (newFilters: TransactionQueryParams) => {
    setFilters(newFilters);
  };

  const applyFilters = () => {
    setAppliedFilters(filters);
  };

  const updateAndApplyFilters = (newFilters: TransactionQueryParams) => {
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
    ethWallets,
    btcWallets,
    baseWallets,
    isLoading,
    isLoadingMore: isFetchingNextPage,
    filters,
    hasActiveFilters,
    totalCount,
    hasNextPage: hasNextPage ?? false,
    updateFilters,
    applyFilters,
    updateAndApplyFilters,
    clearFilters,
    loadMore,
    refetch,
  };
}
