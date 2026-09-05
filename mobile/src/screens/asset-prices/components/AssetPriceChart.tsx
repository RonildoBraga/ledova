import React, { useMemo } from 'react';
import { View, ActivityIndicator, Text, TouchableOpacity } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';
import { TIME_RANGES, type TimeRange } from '@ledova/shared';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useChartPointer } from '../../../hooks/useChartPointer';
import type { ChartDataPoint } from '../useAssetPrices';

interface AssetPriceChartProps {
  chartData: ChartDataPoint[];
  isLoading: boolean;
  error: unknown;
  selectedTimeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
  onActivePointChange?: (index: number) => void;
}

export function AssetPriceChart({
  chartData,
  isLoading,
  error,
  selectedTimeRange,
  onTimeRangeChange,
  onActivePointChange,
}: AssetPriceChartProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    timeRangeContainer: {
      flexDirection: 'row',
      justifyContent: 'center',
      marginTop: theme.spacing.md,
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.full,
      padding: 2,
      alignSelf: 'center',
    },
    timeRangeButton: {
      alignItems: 'center',
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
      borderRadius: theme.borderRadius.full,
    },
    timeRangeButtonActive: {
      backgroundColor: theme.colors.interactive.default,
    },
    timeRangeText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    timeRangeTextActive: {
      color: theme.colors.utility.white,
      fontWeight: theme.fontWeight.semibold,
    },
    chartContainer: {
      height: 200,
    },
    centerContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      paddingVertical: 40,
    },
    loadingText: {
      marginTop: 12,
      fontSize: theme.fontSize.base,
      color: theme.colors.text.muted,
    },
    errorText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.status.error.text,
      marginBottom: 4,
    },
    subtextError: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    emptyText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.muted,
      marginBottom: 4,
    },
    subtext: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
  }));
  const { lineData, isPositiveChange } = useMemo(() => {
    if (!chartData || chartData.length === 0) {
      return { lineData: [], isPositiveChange: true };
    }

    const data = chartData.map((point) => ({ value: point.price }));
    const lastPoint = chartData[chartData.length - 1];
    const positive = lastPoint.changePercent >= 0;

    return { lineData: data, isPositiveChange: positive };
  }, [chartData]);

  const basePointerConfig = useChartPointer({
    onActivePointChange,
    dataLength: lineData.length,
  });

  const lineColor = isPositiveChange ? theme.colors.status.success.icon : theme.colors.status.error.icon;

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={theme.colors.interactive.default} />
        <Text style={styles.loadingText}>Loading price history...</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.errorText}>Failed to load price history</Text>
        <Text style={styles.subtextError}>Please check your connection and try again</Text>
      </View>
    );
  }

  if (!lineData.length) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.emptyText}>No price history available</Text>
        <Text style={styles.subtext}>Price data for this asset is not yet available</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.chartContainer}>
        <LineChart
          data={lineData}
          areaChart
          curved
          hideDataPoints
          hideRules
          hideYAxisText
          hideAxesAndRules
          yAxisLabelWidth={0}
          color={lineColor}
          thickness={1.5}
          startFillColor={`${lineColor}60`}
          endFillColor={`${lineColor}00`}
          startOpacity={0.4}
          endOpacity={0}
          adjustToWidth
          width={undefined}
          initialSpacing={0}
          endSpacing={0}
          height={160}
          pointerConfig={{
            ...basePointerConfig,
            pointerColor: lineColor,
          }}
        />
      </View>

      <View style={styles.timeRangeContainer}>
        {TIME_RANGES.map((range) => (
          <TouchableOpacity
            key={range.value}
            style={[styles.timeRangeButton, selectedTimeRange === range.value && styles.timeRangeButtonActive]}
            onPress={() => onTimeRangeChange(range.value)}
          >
            <Text style={[styles.timeRangeText, selectedTimeRange === range.value && styles.timeRangeTextActive]}>
              {range.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}
