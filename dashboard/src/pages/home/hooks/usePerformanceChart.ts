import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getPortfolioSnapshotsTimeSeries,
  portfolioSnapshotPoints,
  CACHE_TIMING,
  TimeRange,
  TIME_RANGES,
  getDateRange,
} from '@ledova/shared';
import apiClient from '@services/apiClient';

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
    select: (response) => portfolioSnapshotPoints(response.data || []),
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
