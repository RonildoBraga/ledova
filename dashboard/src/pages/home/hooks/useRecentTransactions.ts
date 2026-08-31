import { useCallback } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { getTransactions, getTransactionsNextPage } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import apiClient from '@services/apiClient';

const PAGE_SIZE = 5;

export function useRecentTransactions() {
  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ['home-transactions'],
    queryFn: ({ pageParam = 1 }) => getTransactions(apiClient, { page_size: PAGE_SIZE, page: pageParam }),
    getNextPageParam: getTransactionsNextPage,
    initialPageParam: 1,
    staleTime: CACHE_TIMING.VERY_SHORT_STALE_TIME,
    gcTime: CACHE_TIMING.MEDIUM_GC_TIME,
  });

  const list = data?.pages.flatMap((page) => page.data?.results || []) || [];
  const totalCount = data?.pages[0]?.data?.count || 0;

  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  return {
    list,
    totalCount,
    isLoading,
    isLoadingMore: isFetchingNextPage,
    hasNextPage: hasNextPage ?? false,
    loadMore,
  };
}
