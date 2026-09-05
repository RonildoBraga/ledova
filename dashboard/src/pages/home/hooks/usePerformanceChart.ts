import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getPortfolioSnapshotsTimeSeries, CACHE_TIMING, TimeRange, TIME_RANGES, getDateRange } from '@ledova/shared';
import type { PortfolioSnapshot } from '@ledova/shared';
import apiClient from '@services/apiClient';

interface SnapshotPoint {
  dayIndex: number;
  date: string;
  totalMarketValue: number;
  assetValues: Record<string, number>;
  assetQuantities: Record<string, number>;
  assetSymbols: string[];
}

export function usePerformanceChart(portfolioUuid: string | undefined) {
  const [selectedTimeRange, setSelectedTimeRange] = useState<TimeRange>('3M');
  const { start_date, end_date } = getDateRange(selectedTimeRange);

  const snapshotsQuery = useQuery({
    queryKey: ['portfolio-snapshots', portfolioUuid, start_date, end_date],
    queryFn: () =>
      getPortfolioSnapshotsTimeSeries(apiClient, portfolioUuid!, {
        start_date,
        end_date,
        order_by: 'snapshot_date',
      }),
    enabled: !!portfolioUuid,
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
        } as SnapshotPoint;
      });
    },
  });

  return {
    chartData: snapshotsQuery.data || null,
    selectedTimeRange,
    setSelectedTimeRange,
    timeRanges: TIME_RANGES,
    isLoading: snapshotsQuery.isLoading,
    isError: snapshotsQuery.isError,
  };
}
