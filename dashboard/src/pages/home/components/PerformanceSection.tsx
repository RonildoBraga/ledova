import { useState, useMemo, useCallback, useEffect } from 'react';
import { useColors } from '@hooks/useColors';
import { useCurrency } from '@hooks/useCurrency';
import { Panel } from '@components/Panel';
import { PortfolioValueChart } from './performance/PortfolioValueChart';
import { HoldingsChart } from './performance/HoldingsChart';
import type { TimeRange } from '@ledova/shared-constants';
import { TIME_RANGES } from '@ledova/shared-constants';

type ViewMode = 'total' | 'by-asset';

interface SnapshotPoint {
  dayIndex: number;
  date: string;
  totalMarketValue: number;
  assetValues: Record<string, number>;
  assetQuantities: Record<string, number>;
  assetSymbols: string[];
}

interface PerformanceSectionProps {
  snapshotData: SnapshotPoint[] | null;
  timeRanges: typeof TIME_RANGES;
  selectedTimeRange: TimeRange;
  onTimeRangeChange: (timeRange: TimeRange) => void;
  isLoading: boolean;
  error: unknown;
}

export function PerformanceSection({
  snapshotData,
  timeRanges,
  selectedTimeRange,
  onTimeRangeChange,
  isLoading,
  error,
}: PerformanceSectionProps) {
  const { formatDisplayCurrency } = useCurrency();
  const colors = useColors();
  const [viewMode, setViewMode] = useState<ViewMode>('total');
  const [activePointIndex, setActivePointIndex] = useState<number | null>(null);

  useEffect(() => {
    if (snapshotData && snapshotData.length > 0) {
      setActivePointIndex(snapshotData.length - 1);
    }
  }, [snapshotData]);

  const handleActivePointChange = useCallback((index: number | null) => {
    if (index !== null) setActivePointIndex(index);
  }, []);

  const chartData = snapshotData
    ? {
        labels: snapshotData.map((snapshot) => {
          const date = new Date(snapshot.date);
          return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }),
        values: snapshotData.map((snapshot) => snapshot.totalMarketValue),
      }
    : null;

  const instrumentData = useMemo(() => {
    if (!snapshotData || snapshotData.length === 0) {
      return { data: [], labels: [], yKeys: [] };
    }

    const allSymbols = new Set<string>();
    snapshotData.forEach((snapshot) => {
      snapshot.assetSymbols.forEach((symbol) => allSymbols.add(symbol));
    });
    const yKeys = Array.from(allSymbols);

    const data = snapshotData.map((snapshot) => {
      const point: Record<string, number> = {};
      yKeys.forEach((symbol) => {
        point[symbol] = snapshot.assetValues[symbol] || 0;
      });
      return point;
    });

    const labels = snapshotData.map((snapshot) => {
      const date = new Date(snapshot.date);
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });

    return { data, labels, yKeys };
  }, [snapshotData]);

  const activeSnapshot = activePointIndex != null && snapshotData ? snapshotData[activePointIndex] : null;
  const isScrubbing = activeSnapshot != null;

  const displayValue = isScrubbing
    ? activeSnapshot.totalMarketValue
    : snapshotData && snapshotData.length > 0
      ? snapshotData[snapshotData.length - 1].totalMarketValue
      : null;

  const periodChangePercent = useMemo(() => {
    if (!snapshotData || snapshotData.length < 2) return null;
    const first = snapshotData[0].totalMarketValue;
    const last = snapshotData[snapshotData.length - 1].totalMarketValue;
    if (first === 0) return null;
    return ((last - first) / first) * 100;
  }, [snapshotData]);

  const scrubbedChangePercent = useMemo(() => {
    if (!isScrubbing || !snapshotData || snapshotData.length === 0) return null;
    const first = snapshotData[0].totalMarketValue;
    if (first === 0) return null;
    return ((activeSnapshot.totalMarketValue - first) / first) * 100;
  }, [isScrubbing, activeSnapshot, snapshotData]);

  const displayChangePercent = isScrubbing ? scrubbedChangePercent : periodChangePercent;
  const isPositiveChange = displayChangePercent !== null ? displayChangePercent >= 0 : true;

  const scrubbedDateLabel = isScrubbing
    ? (() => {
        try {
          const date = new Date(activeSnapshot.date);
          if (isNaN(date.getTime())) return '';
          return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch {
          return '';
        }
      })()
    : null;

  if (isLoading && !snapshotData) {
    return (
      <Panel>
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-surface-tertiary rounded"></div>
          <div className="h-64 bg-surface-tertiary rounded"></div>
        </div>
      </Panel>
    );
  }

  if (error) {
    return (
      <Panel>
        <div className="flex flex-col items-center justify-center py-12">
          <p className="text-error-light mb-2">Failed to load portfolio data</p>
          <p className="text-sm text-text-muted">Please check your connection and try again</p>
        </div>
      </Panel>
    );
  }

  return (
    <Panel>
      {viewMode === 'total' && displayValue !== null && (
        <div className="flex flex-col items-center pt-2 mb-2">
          <span className="text-2xl font-bold text-text-primary">{formatDisplayCurrency(displayValue)}</span>
          {displayChangePercent !== null && (
            <span
              className={`mt-1 px-2 py-0.5 rounded-full text-sm font-semibold ${
                isPositiveChange ? 'bg-success-light/20 text-success-light' : 'bg-error-light/20 text-error-light'
              }`}
            >
              {isPositiveChange ? '+' : ''}
              {displayChangePercent.toFixed(2)}%
            </span>
          )}
          {scrubbedDateLabel && <span className="mt-1 text-xs text-text-muted">{scrubbedDateLabel}</span>}
        </div>
      )}

      {viewMode === 'by-asset' && isScrubbing && activeSnapshot && (
        <div className="flex flex-col items-center pt-2 mb-2">
          <span className="text-sm font-semibold text-text-primary">{scrubbedDateLabel}</span>
          <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 mt-1">
            {instrumentData.yKeys.map((symbol, index) => {
              const value = activeSnapshot.assetValues[symbol] || 0;
              const color = colors.chart[index % colors.chart.length];
              return (
                <span key={symbol} className="flex items-center gap-1 text-xs text-text-secondary">
                  <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                  {symbol}: ${value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                </span>
              );
            })}
          </div>
        </div>
      )}

      <div className="min-h-[280px]">
        {viewMode === 'total' && (
          <PortfolioValueChart
            chartData={chartData}
            isLoading={isLoading}
            error={error}
            onActivePointChange={handleActivePointChange}
          />
        )}
        {viewMode === 'by-asset' && (
          <HoldingsChart
            instrumentData={instrumentData}
            isLoading={isLoading}
            onActivePointChange={handleActivePointChange}
          />
        )}
      </div>

      <div className="flex items-center justify-center gap-2 pt-3 mt-2 border-t border-border-subtle">
        <div className="flex bg-surface-tertiary rounded-full p-0.5">
          <button
            type="button"
            onClick={() => setViewMode('total')}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
              viewMode === 'total' ? 'bg-brand-mid text-white font-semibold' : 'text-text-muted'
            }`}
          >
            Total
          </button>
          <button
            type="button"
            onClick={() => setViewMode('by-asset')}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
              viewMode === 'by-asset' ? 'bg-brand-mid text-white font-semibold' : 'text-text-muted'
            }`}
          >
            Holdings
          </button>
        </div>

        <div className="flex bg-surface-tertiary rounded-full p-0.5">
          {timeRanges.map((range) => (
            <button
              key={range.value}
              type="button"
              onClick={() => onTimeRangeChange(range.value)}
              className={`px-2 py-1.5 text-xs font-medium rounded-full transition-colors ${
                selectedTimeRange === range.value
                  ? 'bg-brand-mid text-white font-semibold'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>
    </Panel>
  );
}
