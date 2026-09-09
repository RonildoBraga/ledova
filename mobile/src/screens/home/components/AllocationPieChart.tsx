import { useState } from 'react';
import { View, Text } from 'react-native';
import { PieChart } from 'react-native-gifted-charts';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useCurrency } from '../../../hooks/useCurrency';
import type { AssetAllocationItem } from '@ledova/shared';
import { formatPercentage, VALUE_SOURCE_LABELS } from '@ledova/shared';

interface AllocationPieChartProps {
  data: AssetAllocationItem[];
  totalValue: number;
  isLoading: boolean;
}

export function AllocationPieChart({ data, totalValue, isLoading }: AllocationPieChartProps) {
  const [selectedUuid, setSelectedUuid] = useState<string | null>(null);
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
    unpricedNote: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
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

  const unpricedCount = data.filter((item) => item.basis === 'unpriced').length;

  const drawn = data.filter((item) => item.percentage != null && item.color && item.percentage > 0);
  const selected = drawn.find((item) => item.assetUuid === selectedUuid);
  const sourceDescription = (item: AssetAllocationItem) =>
    `${item.symbol}: ${VALUE_SOURCE_LABELS[item.source]}, ${formatPercentage(item.percentage, 1)}${item.basis === 'quantity' ? ' by quantity' : item.basis === 'unpriced' ? ', incomplete valuation' : ' by value'}`;
  const chartData = drawn.map((item) => ({
    value: item.percentage,
    color: item.color,
    text: item.symbol || '',
    onPress: () => setSelectedUuid((previous) => (previous === item.assetUuid ? null : item.assetUuid)),
  }));

  return (
    <View style={styles.container}>
      <View style={styles.chartWrapper} accessible accessibilityLabel={drawn.map(sourceDescription).join('. ')}>
        <PieChart
          data={chartData}
          donut
          innerRadius={pieChartSize * 0.3}
          radius={pieChartSize * 0.5}
          innerCircleColor={theme.colors.surface.base}
          centerLabelComponent={() => (
            <View style={styles.centerLabel}>
              <Text style={styles.totalValue}>{selected ? selected.symbol : formatDisplayCurrency(totalValue)}</Text>
              <Text style={styles.totalLabel}>{selected ? VALUE_SOURCE_LABELS[selected.source] : 'Total'}</Text>
              {selected ? (
                <Text style={styles.unpricedNote}>
                  {formatPercentage(selected.percentage, 1)} by {selected.basis === 'quantity' ? 'quantity' : 'value'}
                </Text>
              ) : (
                unpricedCount > 0 && <Text style={styles.unpricedNote}>excludes {unpricedCount} unpriced</Text>
              )}
            </View>
          )}
        />
      </View>
    </View>
  );
}

const pieChartSize = 180;
