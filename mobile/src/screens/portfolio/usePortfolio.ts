import { useState } from 'react';
import { useQuery, useQueries } from '@tanstack/react-query';
import {
  getWalletHoldings,
  getWallets,
  getPortfolioSnapshotsTimeSeries,
  CACHE_TIMING,
  TimeRange,
  TIME_RANGES,
  MAX_CHART_POINTS,
  getDateRange,
  calculateHoldingsSummary,
  calculateAssetAllocation,
} from '@ledova/shared';
import { apiClient } from '../../services/apiClient';
import type { HoldingWithWallet, PortfolioSnapshot, Wallet, WalletHolding } from '@ledova/shared';
import { generateMockHoldingsData, generateMockPortfolioChartData } from './_mock/mock';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { useMockData } from '../../_mock/useMockData';

export function usePortfolio() {
  const USE_MOCK_DATA = useMockData();
  const { selectedPortfolio } = useUserPreferences();
  const [selectedTimeRange, setSelectedTimeRange] = useState<TimeRange>('3M');
  const { start_date, end_date } = getDateRange(selectedTimeRange);
  // Fetch all wallets (always called to satisfy React Hooks rules)
  const { data: walletsResponse, isLoading: isLoadingWallets } = useQuery({
    queryKey: ['wallets'],
    queryFn: () => getWallets(apiClient),
    enabled: !USE_MOCK_DATA,
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const wallets = walletsResponse?.data?.results || [];

  // Fetch holdings for all wallets using useQueries (always called to satisfy React Hooks rules)
  const holdingsQueries = useQueries({
    queries: USE_MOCK_DATA
      ? []
      : wallets.map((wallet: Wallet) => ({
          queryKey: ['walletHoldings', wallet.uuid],
          queryFn: () => getWalletHoldings(apiClient, wallet.uuid),
          enabled: !!wallet.uuid,
          staleTime: CACHE_TIMING.SHORT_STALE_TIME,
          gcTime: CACHE_TIMING.MEDIUM_GC_TIME,
        })),
  });

  // Fetch portfolio snapshots for chart data
  const portfolioSnapshotsQuery = useQuery({
    queryKey: ['portfolio-snapshots', selectedPortfolio?.uuid, start_date, end_date],
    queryFn: () =>
      getPortfolioSnapshotsTimeSeries(apiClient, selectedPortfolio!.uuid, {
        start_date,
        end_date,
        order_by: 'snapshot_date',
        max_points: MAX_CHART_POINTS,
      }),
    enabled: !!selectedPortfolio?.uuid && !USE_MOCK_DATA,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    select: (response) => {
      const snapshots = (response.data || []) as PortfolioSnapshot[];
      return snapshots.map((snapshot, index) => {
        const holdingsData = snapshot.holdingsData || {};
        const assetQuantities: Record<string, number> = {};
        const assetValues: Record<string, number> = {};
        let totalMarketValue = snapshot.totalMarketValue ? parseFloat(snapshot.totalMarketValue) : 0;

        Object.entries(holdingsData).forEach(([symbol, holding]) => {
          if (!holding) return;
          assetQuantities[symbol] = parseFloat(holding.quantity || '0');
          const marketValue = parseFloat(holding.marketValue || '0');
          assetValues[symbol] = marketValue;
          if (!snapshot.totalMarketValue) totalMarketValue += marketValue;
        });

        return {
          dayIndex: index,
          date: snapshot.snapshotDate,
          totalMarketValue,
          assetValues,
          assetQuantities,
          assetSymbols: Object.keys(holdingsData),
        };
      });
    },
  });

  // Return mock data if flag is enabled
  if (USE_MOCK_DATA) {
    const mockChartData = generateMockPortfolioChartData(selectedTimeRange);
    return {
      ...generateMockHoldingsData(),
      chartData: mockChartData,
      timeRanges: TIME_RANGES,
      selectedTimeRange,
      onTimeRangeChange: setSelectedTimeRange,
    };
  }

  // Combine all holdings with wallet information
  const holdings: HoldingWithWallet[] = holdingsQueries.flatMap((query, index) => {
    const responseData = (
      query.data as
        | {
            data?: WalletHolding[] | { results?: WalletHolding[] };
          }
        | undefined
    )?.data;
    const holdingsData = Array.isArray(responseData) ? responseData : responseData?.results || [];
    const wallet = wallets[index];

    return holdingsData.map((holding: WalletHolding) => ({
      ...holding,
      walletInfo: {
        uuid: wallet?.uuid || '',
        name: wallet?.name,
        address: wallet?.address || '',
        chain: wallet?.chain || '',
      },
    }));
  });

  // Calculate summary with asset type breakdown
  const summary = calculateHoldingsSummary(holdings, wallets.length);

  // Calculate asset allocation (grouped by asset, not by wallet)
  const assetAllocation = calculateAssetAllocation(holdings, summary.totalValue);

  const isLoading = isLoadingWallets || holdingsQueries.some((query) => query.isLoading);
  const hasError = holdingsQueries.some((query) => query.error);

  return {
    holdings,
    summary,
    assetAllocation,
    isLoading,
    hasError,
    chartData: portfolioSnapshotsQuery.data || null,
    timeRanges: TIME_RANGES,
    selectedTimeRange,
    onTimeRangeChange: setSelectedTimeRange,
  };
}
