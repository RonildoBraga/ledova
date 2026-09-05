import { useState, useMemo, useCallback } from 'react';
import { useQuery, useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import {
  getPortfolioSnapshotsTimeSeries,
  getWallets,
  getTransactions,
  getTransactionsNextPage,
  getAssetByUuid,
  getAssets,
  getFavouriteAssets,
} from '@ledova/shared-services';
import { CACHE_TIMING, TimeRange, TIME_RANGES, BLOCKCHAIN } from '@ledova/shared-constants';
import type { FavouriteAsset, PortfolioSnapshot } from '@ledova/shared-types';
import { getDateRange, calculateWalletTotals, filterWalletsByChain } from '@ledova/shared-utils';
import { apiClient } from '../../services/apiClient';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { usePortfolio } from '../portfolio/usePortfolio';

export const useHome = () => {
  const queryClient = useQueryClient();
  const { selectedPortfolio, selectedAccount, isLoading: preferencesLoading } = useUserPreferences();
  const [selectedTimeRange, setSelectedTimeRange] = useState<TimeRange>('3M');
  const [selectedAssetUuid, setSelectedAssetUuid] = useState<string | null>(null);
  const { start_date, end_date } = getDateRange(selectedTimeRange);

  const holdings = usePortfolio();

  const assetQuantities = useMemo(() => {
    const quantities: Record<string, number> = {};
    holdings.holdings.forEach((holding) => {
      const symbol = holding.assetSymbol || holding.asset?.symbol;
      if (symbol) {
        quantities[symbol] = (quantities[symbol] || 0) + parseFloat(holding.quantity || '0');
      }
    });
    return quantities;
  }, [holdings.holdings]);

  const assetQuery = useQuery({
    queryKey: ['asset', selectedAssetUuid],
    queryFn: () => getAssetByUuid(apiClient, selectedAssetUuid!),
    enabled: !!selectedAssetUuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });

  const walletsQuery = useQuery({
    queryKey: ['wallets', selectedAccount?.uuid],
    queryFn: () => getWallets(apiClient, { user_account: selectedAccount!.uuid }),
    enabled: !!selectedAccount?.uuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const walletsList = walletsQuery.data?.data.results || [];

  const btcWallets = useMemo(() => filterWalletsByChain(walletsList, BLOCKCHAIN.BITCOIN), [walletsList]);
  const ethWallets = useMemo(() => filterWalletsByChain(walletsList, BLOCKCHAIN.ETHEREUM), [walletsList]);
  const baseWallets = useMemo(() => filterWalletsByChain(walletsList, BLOCKCHAIN.BASE), [walletsList]);
  const walletTotals = useMemo(() => calculateWalletTotals(walletsList), [walletsList]);

  const TRANSACTIONS_PAGE_SIZE = 5;
  const transactionsQuery = useInfiniteQuery({
    queryKey: ['home-transactions'],
    queryFn: ({ pageParam = 1 }) => getTransactions(apiClient, { page_size: TRANSACTIONS_PAGE_SIZE, page: pageParam }),
    getNextPageParam: getTransactionsNextPage,
    initialPageParam: 1,
    staleTime: CACHE_TIMING.VERY_SHORT_STALE_TIME,
    gcTime: CACHE_TIMING.MEDIUM_GC_TIME,
  });

  const marketAssetsQuery = useQuery({
    queryKey: ['home-market-assets'],
    queryFn: () => getAssets(apiClient, { is_active: 'true', order_by: 'favourites_first' }),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const marketAssets = marketAssetsQuery.data?.data?.results ?? [];

  const favouritesQuery = useQuery({
    queryKey: ['favouriteAssets'],
    queryFn: () => getFavouriteAssets(apiClient),
    enabled: !!selectedAccount?.uuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const favouriteAssetUuids = useMemo<Set<string>>(
    () => new Set<string>((favouritesQuery.data?.data?.results ?? []).map((f: FavouriteAsset) => f.asset.uuid)),
    [favouritesQuery.data],
  );

  const transactionsList = transactionsQuery.data?.pages.flatMap((page) => page.data?.results || []) || [];
  const transactionsCount = transactionsQuery.data?.pages[0]?.data?.count || 0;

  const loadMoreTransactions = useCallback(() => {
    if (transactionsQuery.hasNextPage && !transactionsQuery.isFetchingNextPage) {
      transactionsQuery.fetchNextPage();
    }
  }, [transactionsQuery]);

  const portfolioSnapshotsQuery = useQuery({
    queryKey: ['portfolio-snapshots', selectedPortfolio?.uuid, start_date, end_date],
    queryFn: () =>
      getPortfolioSnapshotsTimeSeries(apiClient, selectedPortfolio!.uuid, {
        start_date,
        end_date,
        order_by: 'snapshot_date',
      }),
    enabled: !!selectedPortfolio?.uuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    select: (response) => {
      const snapshots = (response.data || []) as PortfolioSnapshot[];
      return snapshots.map((snapshot, index) => {
        const holdingsData = snapshot.holdingsData || {};
        const snapshotQuantities: Record<string, number> = {};
        const assetValues: Record<string, number> = {};
        let totalMarketValue = snapshot.totalMarketValue ? parseFloat(snapshot.totalMarketValue) : 0;

        Object.entries(holdingsData).forEach(([symbol, holding]) => {
          if (!holding) return;
          snapshotQuantities[symbol] = parseFloat(holding.quantity || '0');
          const marketValue = parseFloat(holding.marketValue || '0');
          assetValues[symbol] = marketValue;
          if (!snapshot.totalMarketValue) totalMarketValue += marketValue;
        });

        return {
          dayIndex: index,
          date: snapshot.snapshotDate,
          totalMarketValue,
          assetValues,
          assetQuantities: snapshotQuantities,
          assetSymbols: Object.keys(holdingsData),
        };
      });
    },
  });

  const isHomeLoading = preferencesLoading || portfolioSnapshotsQuery.isLoading;

  const invalidateAll = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['portfolio-snapshots'] }),
      queryClient.invalidateQueries({ queryKey: ['wallets'] }),
      queryClient.invalidateQueries({ queryKey: ['home-transactions'] }),
      queryClient.invalidateQueries({ queryKey: ['home-market-assets'] }),
      queryClient.invalidateQueries({ queryKey: ['favouriteAssets'] }),
      queryClient.invalidateQueries({ queryKey: ['holdings'] }),
    ]);
  }, [queryClient]);

  return {
    invalidateAll,
    isLoading: isHomeLoading,
    error: portfolioSnapshotsQuery.error || null,
    performanceTimeRange: selectedTimeRange,
    setPerformanceTimeRange: setSelectedTimeRange,
    performanceChartData: portfolioSnapshotsQuery.data || null,
    timeRanges: TIME_RANGES,
    holdings,
    assetQuantities,
    selectedAsset: assetQuery.data?.data || null,
    setSelectedAssetUuid,
    wallets: {
      list: walletsList,
      btcWalletsCount: btcWallets.length,
      ethWalletsCount: ethWallets.length,
      baseWalletsCount: baseWallets.length,
      totals: walletTotals,
      isLoading: walletsQuery.isLoading,
    },
    marketAssets,
    favouriteAssetUuids,
    isMarketAssetsLoading: marketAssetsQuery.isLoading,
    transactions: {
      list: transactionsList,
      totalCount: transactionsCount,
      isLoading: transactionsQuery.isLoading,
      isLoadingMore: transactionsQuery.isFetchingNextPage,
      hasNextPage: transactionsQuery.hasNextPage ?? false,
      loadMore: loadMoreTransactions,
    },
  };
};
