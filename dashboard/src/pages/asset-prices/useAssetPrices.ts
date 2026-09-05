import { useState, useCallback, useMemo } from 'react';
import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import {
  getAssets,
  getAssetsNextPage,
  getAssetSnapshots,
  CACHE_TIMING,
  type TimeRange,
  getDateRange,
} from '@ledova/shared';
import type { ChartDataPoint, AssetQueryParams } from '@ledova/shared';
import apiClient from '@services/apiClient';

export type { ChartDataPoint };

export interface AssetFilters {
  search?: string;
  asset_type?: string;
  chain?: string;
}

const DEFAULT_FILTERS: AssetFilters = {};

export function useAssetPrices() {
  const [filters, setFilters] = useState<AssetFilters>(DEFAULT_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<AssetFilters>(DEFAULT_FILTERS);

  // Build query params from applied filters
  const buildQueryParams = (filters: AssetFilters): AssetQueryParams => {
    const params: AssetQueryParams = {
      is_active: 'true',
      order_by: 'symbol',
    };

    if (filters.search) {
      params.search = filters.search;
    }
    if (filters.asset_type) {
      params.asset_type = filters.asset_type;
    }
    if (filters.chain) {
      params.chain = filters.chain;
    }

    return params;
  };

  // Fetch assets with infinite query for pagination
  const {
    data: assetsData,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ['assets', appliedFilters],
    queryFn: ({ pageParam = 1 }) => getAssets(apiClient, { ...buildQueryParams(appliedFilters), page: pageParam }),
    getNextPageParam: getAssetsNextPage,
    initialPageParam: 1,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.LONG_GC_TIME,
  });

  // Flatten all pages into a single array
  const assets = assetsData?.pages.flatMap((page) => page.data?.results || []) || [];
  const totalCount = assetsData?.pages[0]?.data?.count || 0;

  const hasActiveFilters = Object.keys(appliedFilters).some(
    (key) => appliedFilters[key as keyof AssetFilters] !== undefined,
  );

  const updateAndApplyFilters = useCallback((newFilters: AssetFilters) => {
    setFilters(newFilters);
    setAppliedFilters(newFilters);
  }, []);

  const clearFilters = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
    setAppliedFilters(DEFAULT_FILTERS);
  }, []);

  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  return {
    assets,
    filters,
    hasActiveFilters,
    totalCount,
    hasNextPage: hasNextPage ?? false,
    updateAndApplyFilters,
    clearFilters,
    loadMore,
    isLoading,
    isLoadingMore: isFetchingNextPage,
    refetch,
  };
}

export function useAssetPriceHistory(assetUuid: string | null) {
  const [selectedTimeRange, setSelectedTimeRange] = useState<TimeRange>('3M');

  const { start_date, end_date } = useMemo(() => getDateRange(selectedTimeRange), [selectedTimeRange]);

  const snapshotsQuery = useQuery({
    queryKey: ['asset-snapshots', assetUuid, start_date, end_date],
    queryFn: () =>
      getAssetSnapshots(apiClient, assetUuid!, {
        start_date,
        end_date,
        limit: 0, // No limit - date range already constrains the data
        order_by: 'source_timestamp', // Oldest first for chronological chart display
      }),
    enabled: !!assetUuid,
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
    gcTime: CACHE_TIMING.MEDIUM_GC_TIME,
  });

  const { chartData, periodChangePercent } = useMemo(() => {
    const snapshots = snapshotsQuery.data?.data || [];
    if (snapshots.length === 0) return { chartData: [], periodChangePercent: null };

    const firstPrice = parseFloat(snapshots[0].price) || 0;

    const data: ChartDataPoint[] = snapshots.map(
      (snapshot: { price: string; sourceTimestamp: string }, index: number) => {
        const price = parseFloat(snapshot.price) || 0;
        // Calculate change from start of period
        const changePercent = firstPrice > 0 ? ((price - firstPrice) / firstPrice) * 100 : 0;

        return {
          dayIndex: index,
          date: snapshot.sourceTimestamp,
          price,
          changePercent,
        };
      },
    );

    // Calculate overall period change (first to last)
    const lastPrice = parseFloat(snapshots[snapshots.length - 1].price) || 0;
    const overallChange = firstPrice > 0 ? ((lastPrice - firstPrice) / firstPrice) * 100 : null;

    return { chartData: data, periodChangePercent: overallChange };
  }, [snapshotsQuery.data?.data]);

  return {
    chartData,
    periodChangePercent,
    selectedTimeRange,
    setSelectedTimeRange,
    isLoading: snapshotsQuery.isLoading,
    error: snapshotsQuery.error,
  };
}
