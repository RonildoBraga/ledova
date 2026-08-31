import { View, Text } from 'react-native';
import { PieChart } from 'react-native-gifted-charts';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useCurrency } from '../../../hooks/useCurrency';
import type { AssetAllocationItem } from '@ledova/shared-types';

interface AllocationPieChartProps {
  data: AssetAllocationItem[];
  totalValue: number;
  isLoading: boolean;
}

export function AllocationPieChart({ data, totalValue, isLoading }: AllocationPieChartProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    container: {
      height: '100%',
      justifyContent: 'center',
      alignItems: 'center',
    },
    chartWrapper: {
      width: pieChartSize,
      height: pieChartSize,
      justifyContent: 'center',
      alignItems: 'center',
    },
    centerLabel: {
      justifyContent: 'center',
      alignItems: 'center',
    },
    totalValue: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
    },
    totalLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    emptyContainer: {
      minHeight: 250,
      justifyContent: 'center',
      alignItems: 'center',
    },
    emptyText: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.muted,
      marginBottom: theme.spacing.xs,
    },
    subtext: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
  }));
  if (isLoading || data.length === 0) {
    return (
      <View style={styles.emptyContainer}>
        <Text style={styles.emptyText}>No allocation data available</Text>
        <Text style={styles.subtext}>Add wallets with transactions to track asset values</Text>
      </View>
    );
  }

  const chartData = data
    .filter((item) => item.percentage != null && item.color && item.percentage > 0)
    .map((item) => ({
      value: item.percentage,
      color: item.color,
      text: item.symbol || '',
    }));

  return (
    <View style={styles.container}>
      <View style={styles.chartWrapper}>
        <PieChart
          data={chartData}
          donut
          innerRadius={pieChartSize * 0.3}
          radius={pieChartSize * 0.5}
          innerCircleColor={theme.colors.surface.base}
          centerLabelComponent={() => (
            <View style={styles.centerLabel}>
              <Text style={styles.totalValue}>{formatDisplayCurrency(totalValue)}</Text>
              <Text style={styles.totalLabel}>Total</Text>
            </View>
          )}
        />
      </View>
    </View>
  );
}

const pieChartSize = 180;
