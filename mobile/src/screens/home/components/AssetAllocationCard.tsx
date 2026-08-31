import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { WalletIcon } from 'phosphor-react-native';
import { Panel } from '../../../components/panel';
import { AllocationPieChart } from './AllocationPieChart';
import { ErrorBoundary } from '../../../components/ErrorBoundary';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { formatPercentage } from '@ledova/shared-utils';
import { useCurrency } from '../../../hooks/useCurrency';
import type { AssetAllocationItem, HoldingsSummary } from '@ledova/shared-types';

interface AssetAllocationCardProps {
  assetAllocation: AssetAllocationItem[];
  totalValue: number;
  summary: HoldingsSummary;
  assetQuantities: Record<string, number>;
  isLoading: boolean;
  hasError: boolean;
  onAssetClick: (assetUuid: string) => void;
}

export function AssetAllocationCard({
  assetAllocation,
  totalValue,
  summary,
  assetQuantities,
  isLoading,
  hasError,
  onAssetClick,
}: AssetAllocationCardProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    panelContent: {
      minHeight: 200,
    },
    chartContainer: {
      height: 200,
    },
    holdingsList: {
      paddingHorizontal: theme.spacing.sm,
      gap: theme.spacing.xs,
    },
    holdingRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
    },
    colorDot: {
      width: theme.spacing.sm,
      height: theme.spacing.sm,
      borderRadius: theme.borderRadius.full,
    },
    holdingSymbol: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
    },
    navText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    rightGroup: {
      flex: 1,
      flexDirection: 'row',
      justifyContent: 'flex-end',
      alignItems: 'baseline',
      gap: theme.spacing.sm,
    },
    quantityText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    holdingValue: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    percentageText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      minWidth: 36,
      textAlign: 'right',
    },
    loadingContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.sm,
      paddingVertical: theme.spacing.lg,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    emptyState: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.lg,
      gap: theme.spacing.xs,
    },
    emptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    emptySubtext: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
  }));
  const formatQuantity = (quantity: number) => {
    return quantity.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 6,
    });
  };

  const renderLoading = () => (
    <View style={styles.loadingContainer}>
      <ActivityIndicator size="small" color={theme.colors.interactive.active} />
      <Text style={styles.loadingText}>Loading allocation...</Text>
    </View>
  );

  const renderEmpty = () => (
    <View style={styles.emptyState}>
      <WalletIcon size={theme.icon.sizes.xl} color={theme.colors.text.subtle} weight={theme.icon.weights.light} />
      <Text style={styles.emptyText}>No holdings yet</Text>
      <Text style={styles.emptySubtext}>Add wallets to see allocation</Text>
    </View>
  );

  const renderError = () => (
    <View style={styles.emptyState}>
      <Text style={styles.emptyText}>Failed to load holdings</Text>
    </View>
  );

  const renderContent = () => (
    <View>
      <View style={styles.chartContainer}>
        <ErrorBoundary fallback={<View />}>
          <AllocationPieChart data={assetAllocation} totalValue={totalValue} isLoading={false} />
        </ErrorBoundary>
      </View>

      <View style={styles.holdingsList}>
        {assetAllocation.map((item) => {
          const quantity = assetQuantities[item.symbol];
          const hasQuantity = quantity !== undefined && quantity > 0;
          const showQuantity = hasQuantity && !(item.totalValue > 0 && Math.abs(quantity / item.totalValue - 1) < 0.05);

          return (
            <TouchableOpacity
              key={item.assetUuid}
              style={styles.holdingRow}
              onPress={() => onAssetClick(item.assetUuid)}
              activeOpacity={0.7}
            >
              <View style={[styles.colorDot, { backgroundColor: item.color }]} />
              <View>
                <Text style={styles.holdingSymbol}>{item.name}</Text>
                {item.isYieldToken && item.navPerToken && (
                  <Text style={styles.navText}>NAV: ${parseFloat(item.navPerToken).toFixed(6)}</Text>
                )}
              </View>
              <View style={styles.rightGroup}>
                {showQuantity && <Text style={styles.quantityText}>{formatQuantity(quantity)}</Text>}
                <Text style={styles.holdingValue}>{formatDisplayCurrency(item.totalValue)}</Text>
                <Text style={styles.percentageText}>{formatPercentage(item.percentage, 1)}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );

  return (
    <Panel>
      <View style={styles.panelContent}>
        {isLoading
          ? renderLoading()
          : hasError
            ? renderError()
            : summary.holdingsCount === 0
              ? renderEmpty()
              : renderContent()}
      </View>
    </Panel>
  );
}
