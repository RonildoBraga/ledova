import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getAssetByUuid,
  getAssets,
  getFavouriteAssets,
  BLOCKCHAIN,
  CACHE_TIMING,
  calculateWalletTotals,
  filterWalletsByChain,
} from '@ledova/shared';
import type { Asset } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { useSelectedPortfolio } from '@hooks/useSelectedPortfolio';
import { useWalletsSummary } from './hooks/useWalletsSummary';
import { useHoldings } from './hooks/useHoldings';
import { useRecentTransactions } from './hooks/useRecentTransactions';
import { usePerformanceChart } from './hooks/usePerformanceChart';

export function useHome() {
  const { selectedPortfolio, selectedAccount, isLoading: preferencesLoading } = useSelectedPortfolio();

  const walletsSummary = useWalletsSummary(selectedAccount?.uuid);
  const holdings = useHoldings(walletsSummary.walletsList);
  const transactions = useRecentTransactions();
  const performance = usePerformanceChart(selectedPortfolio?.uuid);

  const [selectedAssetUuid, setSelectedAssetUuid] = useState<string | null>(null);

  const assetQuery = useQuery({
    queryKey: ['asset', selectedAssetUuid],
    queryFn: () => getAssetByUuid(apiClient, selectedAssetUuid!),
    enabled: !!selectedAssetUuid,
  });

  const selectedAsset: Asset | null = assetQuery.data?.data || null;

  const marketAssetsQuery = useQuery({
    queryKey: ['home-market-assets'],
    queryFn: () => getAssets(apiClient, { is_active: 'true', order_by: 'favourites_first' }),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const favouritesQuery = useQuery({
    queryKey: ['favouriteAssets'],
    queryFn: () => getFavouriteAssets(apiClient),
    enabled: !!selectedAccount?.uuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const favouriteAssetUuids = useMemo(
    () => new Set((favouritesQuery.data?.data?.results ?? []).map((f) => f.asset.uuid)),
    [favouritesQuery.data],
  );

  return {
    isLoading: preferencesLoading || performance.isLoading,
    isError: performance.isError,
    performanceTimeRange: performance.selectedTimeRange,
    setPerformanceTimeRange: performance.setSelectedTimeRange,
    performanceChartData: performance.chartData,
    timeRanges: performance.timeRanges,
    holdings: {
      summary: holdings.summary,
      assetAllocation: holdings.assetAllocation,
      assetQuantities: holdings.assetQuantities,
      isLoading: walletsSummary.isLoading || holdings.isLoading,
      hasError: holdings.hasError,
    },
    selectedAsset,
    setSelectedAssetUuid,
    wallets: {
      btcWalletsCount: filterWalletsByChain(walletsSummary.walletsList, BLOCKCHAIN.BITCOIN).length,
      ethWalletsCount: filterWalletsByChain(walletsSummary.walletsList, BLOCKCHAIN.ETHEREUM).length,
      totals: calculateWalletTotals(walletsSummary.walletsList),
      isLoading: walletsSummary.isLoading,
    },
    transactions,
    marketAssets: marketAssetsQuery.data?.data?.results ?? [],
    favouriteAssetUuids,
    isMarketAssetsLoading: marketAssetsQuery.isLoading,
  };
}
