import { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView } from 'react-native';
import { PortfolioLineChart } from './PortfolioLineChart';
import { AssetLineChart } from './AssetLineChart';
import { ErrorBoundary } from '../../../components/ErrorBoundary';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useCurrency } from '../../../hooks/useCurrency';
import type { TimeRange } from '@ledova/shared-constants';
import type { PortfolioSnapshotDataPoint } from '@ledova/shared-types';

interface PerformanceCardProps {
  chartData: PortfolioSnapshotDataPoint[] | null;
  totalValue?: number;
  timeRanges: Array<{ label: string; months?: number | null }>;
  selectedTimeRange: TimeRange;
  onTimeRangeChange: (timeRange: TimeRange) => void;
  isLoading: boolean;
  error: unknown;
  assetColorMap: Record<string, string>;
}

function computeChangePercent(data: PortfolioSnapshotDataPoint[] | null, activeIndex: number | null): number | null {
  if (!data || data.length < 2) return null;
  const first = data[0].totalMarketValue;
  if (first === 0) return null;
  const current = activeIndex != null ? data[activeIndex]?.totalMarketValue : data[data.length - 1].totalMarketValue;
  if (current == null) return null;
  return ((current - first) / first) * 100;
}

function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '';
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return '';
  }
}

function ChartErrorFallback() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    centerContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.muted,
      marginBottom: theme.spacing.xs,
    },
    subtext: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
  }));
  return (
    <View style={styles.centerContainer}>
      <Text style={styles.errorText}>Chart unavailable</Text>
      <Text style={styles.subtext}>Please try again later</Text>
    </View>
  );
}

export function PerformanceCard({
  chartData,
  totalValue,
  timeRanges,
  selectedTimeRange,
  onTimeRangeChange,
  isLoading,
  error,
  assetColorMap,
}: PerformanceCardProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    valueHeader: {
      alignItems: 'center',
      paddingBottom: theme.spacing.xs,
    },
    totalValue: {
      fontSize: theme.fontSize.xxl,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
    },
    headerLabel: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    changeBadge: {
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: 2,
      borderRadius: theme.borderRadius.full,
      marginTop: 2,
    },
    changeBadgePositive: {
      backgroundColor: `${theme.colors.status.success.icon}33`,
    },
    changeBadgeNegative: {
      backgroundColor: `${theme.colors.status.error.icon}33`,
    },
    changeBadgeText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
    },
    changeBadgeTextPositive: {
      color: theme.colors.status.success.icon,
    },
    changeBadgeTextNegative: {
      color: theme.colors.status.error.icon,
    },
    assetBreakdownRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      justifyContent: 'center',
      gap: theme.spacing.sm,
    },
    assetBreakdownItem: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    assetDot: {
      width: theme.spacing.sm,
      height: theme.spacing.sm,
      borderRadius: theme.borderRadius.full,
    },
    assetBreakdownText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    chartContainer: {
      flex: 1,
    },
    centerContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.muted,
      marginBottom: theme.spacing.xs,
    },
    subtext: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
    controlsRow: {
      flexGrow: 0,
      paddingTop: theme.spacing.sm,
    },
    controlsScroll: {
      flexGrow: 1,
      justifyContent: 'center',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    chartToggle: {
      flexDirection: 'row',
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.full,
      padding: 2,
    },
    chartToggleButton: {
      alignItems: 'center',
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
      borderRadius: theme.borderRadius.full,
    },
    chartToggleButtonActive: {
      backgroundColor: theme.colors.interactive.default,
    },
    chartToggleText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    chartToggleTextActive: {
      color: theme.colors.utility.white,
      fontWeight: theme.fontWeight.semibold,
    },
    timeRangeToggle: {
      flexDirection: 'row',
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.full,
      padding: 2,
    },
    timeRangeButton: {
      alignItems: 'center',
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
      borderRadius: theme.borderRadius.full,
    },
    activeTimeRangeButton: {
      backgroundColor: theme.colors.interactive.default,
    },
    timeRangeText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    activeTimeRangeText: {
      color: theme.colors.utility.white,
      fontWeight: theme.fontWeight.semibold,
    },
  }));
  const [chartTab, setChartTab] = useState<'total' | 'by-asset'>('total');
  const [totalActiveIndex, setTotalActiveIndex] = useState<number | null>(null);
  const [assetActiveIndex, setAssetActiveIndex] = useState<number | null>(null);

  const handleTotalPointChange = useCallback((index: number) => {
    setTotalActiveIndex(index);
  }, []);

  const handleAssetPointChange = useCallback((index: number) => {
    setAssetActiveIndex(index);
  }, []);

  const activePointIndex = chartTab === 'total' ? totalActiveIndex : assetActiveIndex;
  const activePoint = activePointIndex != null ? chartData?.[activePointIndex] : null;
  const hasActivePoint = activePoint != null;

  const latestSnapshot = chartData?.[chartData.length - 1];
  const defaultValue = latestSnapshot?.totalMarketValue ?? totalValue ?? 0;

  const displayLabel = hasActivePoint
    ? formatDate(activePoint.date)
    : latestSnapshot?.date
      ? formatDate(latestSnapshot.date)
      : 'Total Value';

  const changePercent = computeChangePercent(chartData, hasActivePoint ? activePointIndex : null);
  const isPositiveChange = changePercent !== null ? changePercent >= 0 : true;

  return (
    <View style={styles.container}>
      <View style={styles.valueHeader}>
        {chartTab === 'by-asset' && (hasActivePoint || latestSnapshot) ? (
          <>
            <View style={styles.assetBreakdownRow}>
              {(hasActivePoint ? activePoint.assetSymbols : latestSnapshot!.assetSymbols).map((symbol) => (
                <View key={symbol} style={styles.assetBreakdownItem}>
                  <View
                    style={[styles.assetDot, { backgroundColor: assetColorMap[symbol] || theme.colors.text.muted }]}
                  />
                  <Text style={styles.assetBreakdownText}>
                    {symbol}{' '}
                    {formatDisplayCurrency(
                      hasActivePoint
                        ? activePoint.assetValues?.[symbol] || 0
                        : latestSnapshot!.assetValues?.[symbol] || 0,
                    )}
                  </Text>
                </View>
              ))}
            </View>
            <Text style={styles.headerLabel}>{displayLabel}</Text>
          </>
        ) : (
          <>
            <Text style={styles.totalValue}>
              {formatDisplayCurrency(hasActivePoint ? activePoint.totalMarketValue || 0 : defaultValue)}
            </Text>
            {changePercent !== null && (
              <View
                style={[styles.changeBadge, isPositiveChange ? styles.changeBadgePositive : styles.changeBadgeNegative]}
              >
                <Text
                  style={[
                    styles.changeBadgeText,
                    isPositiveChange ? styles.changeBadgeTextPositive : styles.changeBadgeTextNegative,
                  ]}
                >
                  {isPositiveChange ? '+' : ''}
                  {changePercent.toFixed(2)}%
                </Text>
              </View>
            )}
            <Text style={styles.headerLabel}>{displayLabel}</Text>
          </>
        )}
      </View>

      <View style={styles.chartContainer}>
        <ErrorBoundary fallback={<ChartErrorFallback />}>
          {chartTab === 'total' && (
            <PortfolioLineChart
              chartData={chartData || undefined}
              isLoading={isLoading}
              error={error}
              onActivePointChange={handleTotalPointChange}
              initialPointerIndex={totalActiveIndex ?? undefined}
            />
          )}
          {chartTab === 'by-asset' && (
            <AssetLineChart
              chartData={chartData || undefined}
              isLoading={isLoading}
              error={error}
              onActivePointChange={handleAssetPointChange}
              assetColorMap={assetColorMap}
              initialPointerIndex={assetActiveIndex ?? undefined}
            />
          )}
        </ErrorBoundary>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.controlsScroll}
        style={styles.controlsRow}
      >
        <View style={styles.chartToggle}>
          <TouchableOpacity
            onPress={() => setChartTab('total')}
            style={[styles.chartToggleButton, chartTab === 'total' && styles.chartToggleButtonActive]}
          >
            <Text style={[styles.chartToggleText, chartTab === 'total' && styles.chartToggleTextActive]}>Total</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setChartTab('by-asset')}
            style={[styles.chartToggleButton, chartTab === 'by-asset' && styles.chartToggleButtonActive]}
          >
            <Text style={[styles.chartToggleText, chartTab === 'by-asset' && styles.chartToggleTextActive]}>
              Holdings
            </Text>
          </TouchableOpacity>
        </View>

        <View style={styles.timeRangeToggle}>
          {timeRanges.map((range) => (
            <TouchableOpacity
              key={range.label}
              onPress={() => onTimeRangeChange(range.label as TimeRange)}
              style={[styles.timeRangeButton, selectedTimeRange === range.label && styles.activeTimeRangeButton]}
            >
              <Text style={[styles.timeRangeText, selectedTimeRange === range.label && styles.activeTimeRangeText]}>
                {range.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}
