import { useMemo } from 'react';
import { View, useWindowDimensions } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';
import type { PortfolioSnapshotDataPoint } from '@ledova/shared';
import { useAppTheme } from '../../../contexts';
import type { lineDataItem } from 'gifted-charts-core';
import { useChartPointer } from '../../../hooks/useChartPointer';
import { ChartStateView, type ChartState } from './ChartStateView';

interface AssetLineChartProps {
  chartData?: PortfolioSnapshotDataPoint[];
  isLoading: boolean;
  error: unknown;
  onActivePointChange?: (index: number) => void;
  assetColorMap: Record<string, string>;
  initialPointerIndex?: number;
}

const STATE_MESSAGES = {
  loadingText: 'Loading asset values...',
  errorText: 'Failed to load asset values',
  errorSubtext: 'Please check your connection and try again',
  emptyText: 'No asset value data available',
  emptySubtext: 'Add wallets with transactions to track asset values',
};

const MAX_CHART_SERIES = 5;
const OTHER_KEY = 'Other';
const CHART_HEIGHT = 220;

export function AssetLineChart({
  chartData,
  isLoading,
  error,
  onActivePointChange,
  assetColorMap,
  initialPointerIndex,
}: AssetLineChartProps) {
  const theme = useAppTheme();
  const { width: screenWidth } = useWindowDimensions();
  const GRID_COLOR = theme.colors.chartUI.gridColor;

  const horizontalPadding = 2 * (theme.spacing.sm + theme.spacing.sm);
  const chartWidth = screenWidth - horizontalPadding;

  const { dataSets, yKeys } = useMemo(() => {
    if (!chartData || chartData.length === 0) {
      return { dataSets: [], yKeys: [] as string[] };
    }

    const latestSnapshot = chartData[chartData.length - 1];
    const allKeys = latestSnapshot.assetSymbols || [];

    const sortedKeys = [...allKeys].sort(
      (a, b) => (latestSnapshot.assetValues?.[b] || 0) - (latestSnapshot.assetValues?.[a] || 0),
    );

    const needsGrouping = sortedKeys.length > MAX_CHART_SERIES;
    const displayKeys = needsGrouping ? sortedKeys.slice(0, MAX_CHART_SERIES - 1) : sortedKeys;
    const otherKeys = needsGrouping ? sortedKeys.slice(MAX_CHART_SERIES - 1) : [];

    const assetDataArrays: Record<string, lineDataItem[]> = {};
    displayKeys.forEach((symbol) => {
      assetDataArrays[symbol] = [];
    });
    if (needsGrouping) {
      assetDataArrays[OTHER_KEY] = [];
    }

    chartData.forEach((snapshot) => {
      displayKeys.forEach((symbol) => {
        assetDataArrays[symbol].push({ value: snapshot.assetValues?.[symbol] || 0 });
      });
      if (needsGrouping) {
        const otherValue = otherKeys.reduce((sum, symbol) => sum + (snapshot.assetValues?.[symbol] || 0), 0);
        assetDataArrays[OTHER_KEY].push({ value: otherValue });
      }
    });

    const finalKeys = needsGrouping ? [...displayKeys, OTHER_KEY] : displayKeys;
    const sets = finalKeys.map((symbol) => ({
      key: symbol,
      data: assetDataArrays[symbol],
      color: symbol === OTHER_KEY ? theme.colors.text.muted : assetColorMap[symbol] || theme.colors.text.muted,
    }));

    return { dataSets: sets, yKeys: finalKeys };
  }, [chartData, assetColorMap, theme.colors.text.muted]);

  const primaryData = dataSets[0]?.data ?? [];
  const primaryColor = dataSets[0]?.color ?? theme.colors.text.muted;
  const secondary = dataSets.slice(1);

  const basePointerConfig = useChartPointer({
    onActivePointChange,
    initialPointerIndex,
    dataLength: primaryData.length,
  });

  const chartState: ChartState | null =
    isLoading && !chartData ? 'loading' : error ? 'error' : !dataSets.length || !yKeys.length ? 'empty' : null;

  if (chartState) return <ChartStateView state={chartState} {...STATE_MESSAGES} />;

  return (
    <View style={{ flex: 1, overflow: 'hidden' }}>
      <LineChart
        data={primaryData}
        data2={secondary[0]?.data}
        color2={secondary[0]?.color}
        data3={secondary[1]?.data}
        color3={secondary[1]?.color}
        data4={secondary[2]?.data}
        color4={secondary[2]?.color}
        data5={secondary[3]?.data}
        color5={secondary[3]?.color}
        curved
        hideDataPoints
        hideYAxisText
        noOfSections={4}
        rulesColor={GRID_COLOR}
        rulesType="dashed"
        dashWidth={theme.spacing.xs}
        dashGap={theme.spacing.xs}
        yAxisLabelWidth={0}
        xAxisColor="transparent"
        yAxisColor="transparent"
        xAxisLabelsHeight={0}
        color={primaryColor}
        thickness={2}
        width={chartWidth}
        spacing={chartWidth / Math.max(primaryData.length - 1, 1)}
        initialSpacing={0}
        height={CHART_HEIGHT}
        pointerConfig={{
          ...basePointerConfig,
          pointerColor: primaryColor,
          pointer1Color: primaryColor,
          pointer2Color: secondary[0]?.color,
          pointer3Color: secondary[1]?.color,
          pointer4Color: secondary[2]?.color,
          pointer5Color: secondary[3]?.color,
        }}
      />
    </View>
  );
}
