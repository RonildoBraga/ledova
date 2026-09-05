import { useMemo } from 'react';
import { View, useWindowDimensions } from 'react-native';
import { LineChart } from 'react-native-gifted-charts';
import type { PortfolioSnapshotDataPoint } from '@ledova/shared';
import { useAppTheme } from '../../../contexts';
import { useChartPointer } from '../../../hooks/useChartPointer';
import { ChartStateView, type ChartState } from './ChartStateView';

interface PortfolioLineChartProps {
  chartData?: PortfolioSnapshotDataPoint[];
  isLoading: boolean;
  error: unknown;
  onActivePointChange?: (index: number) => void;
  initialPointerIndex?: number;
}

const STATE_MESSAGES = {
  loadingText: 'Loading portfolio value...',
  errorText: 'Failed to load portfolio value',
  errorSubtext: 'Please check your connection and try again',
  emptyText: 'No portfolio value yet',
  emptySubtext: 'Add wallets with transactions to see value',
};

const CHART_HEIGHT = 220;

export function PortfolioLineChart({
  chartData,
  isLoading,
  error,
  onActivePointChange,
  initialPointerIndex,
}: PortfolioLineChartProps) {
  const theme = useAppTheme();
  const { width: screenWidth } = useWindowDimensions();
  const LINE_COLOR = theme.colors.chartUI.portfolioLine;
  const GRID_COLOR = theme.colors.chartUI.gridColor;

  // scrollContent padding (sm) + Panel content padding (sm) on each side
  const horizontalPadding = 2 * (theme.spacing.sm + theme.spacing.sm);
  const chartWidth = screenWidth - horizontalPadding;

  const lineData = useMemo(() => {
    if (!chartData || chartData.length === 0) return [];
    return chartData.map((snapshot) => ({ value: snapshot.totalMarketValue || 0 }));
  }, [chartData]);

  const basePointerConfig = useChartPointer({ onActivePointChange, initialPointerIndex });

  const chartState: ChartState | null =
    isLoading && !chartData
      ? 'loading'
      : error
        ? 'error'
        : !lineData.length || !lineData.some((d) => d.value > 0)
          ? 'empty'
          : null;

  if (chartState) return <ChartStateView state={chartState} {...STATE_MESSAGES} />;

  return (
    <View style={{ flex: 1, overflow: 'hidden' }}>
      <LineChart
        data={lineData}
        areaChart
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
        width={chartWidth}
        spacing={chartWidth / Math.max(lineData.length - 1, 1)}
        initialSpacing={0}
        color={LINE_COLOR}
        thickness={2}
        startFillColor={`${LINE_COLOR}60`}
        endFillColor={`${LINE_COLOR}00`}
        startOpacity={0.5}
        endOpacity={0}
        height={CHART_HEIGHT}
        pointerConfig={{
          ...basePointerConfig,
          pointerColor: LINE_COLOR,
        }}
      />
    </View>
  );
}
