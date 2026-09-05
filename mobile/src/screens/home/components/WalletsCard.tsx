import { View, Text, ActivityIndicator } from 'react-native';
import { WalletIcon } from 'phosphor-react-native';
import { PieChart } from 'react-native-gifted-charts';
import { Panel } from '../../../components/panel';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { formatCryptoBalance, formatPercentage } from '@ledova/shared-utils';
import { useCurrency } from '../../../hooks/useCurrency';
import type { WalletTotals } from '@ledova/shared-types';

const PIE_SIZE = 180;

interface WalletAllocationCardProps {
  btcWalletsCount: number;
  ethWalletsCount: number;
  baseWalletsCount: number;
  totals: WalletTotals;
  isLoading: boolean;
}

export function WalletsCard({
  btcWalletsCount,
  ethWalletsCount,
  baseWalletsCount,
  totals,
  isLoading,
}: WalletAllocationCardProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    panelContent: {
      minHeight: 200,
    },
    chartContainer: {
      height: 200,
      justifyContent: 'center',
      alignItems: 'center',
    },
    chartWrapper: {
      width: PIE_SIZE,
      height: PIE_SIZE,
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
    legendList: {
      paddingHorizontal: theme.spacing.sm,
      gap: theme.spacing.xs,
    },
    legendRow: {
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
    chainName: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    rightGroup: {
      flex: 1,
      flexDirection: 'row',
      justifyContent: 'flex-end',
      alignItems: 'baseline',
      gap: theme.spacing.sm,
    },
    cryptoBalance: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    marketValue: {
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

  const totalWallets = btcWalletsCount + ethWalletsCount + baseWalletsCount;
  const totalMarketValue = totals.ethTotalMarketValue + totals.btcTotalMarketValue + totals.baseTotalMarketValue;
  const hasEth = totals.ethTotalMarketValue > 0;
  const hasBtc = totals.btcTotalMarketValue > 0;
  const hasBase = totals.baseTotalMarketValue > 0;
  const percentageOf = (value: number) => (totalMarketValue > 0 ? (value / totalMarketValue) * 100 : 0);
  const ethPercentage = percentageOf(totals.ethTotalMarketValue);
  const btcPercentage = percentageOf(totals.btcTotalMarketValue);
  const basePercentage = percentageOf(totals.baseTotalMarketValue);

  const ETH_COLOR = theme.colors.chain.ethereum;
  const BTC_COLOR = theme.colors.chain.bitcoin;
  const BASE_COLOR = theme.colors.chain.base;

  if (isLoading) {
    return (
      <Panel>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="small" color={theme.colors.interactive.active} />
          <Text style={styles.loadingText}>Loading wallets...</Text>
        </View>
      </Panel>
    );
  }

  if (totalWallets === 0) {
    return (
      <Panel>
        <View style={styles.emptyState}>
          <WalletIcon size={theme.icon.sizes.xl} color={theme.colors.text.subtle} weight={theme.icon.weights.light} />
          <Text style={styles.emptyText}>No wallets yet</Text>
          <Text style={styles.emptySubtext}>Add wallets to see chain allocation</Text>
        </View>
      </Panel>
    );
  }

  const chartData = [
    ...(hasEth ? [{ value: ethPercentage, color: ETH_COLOR }] : []),
    ...(hasBtc ? [{ value: btcPercentage, color: BTC_COLOR }] : []),
    ...(hasBase ? [{ value: basePercentage, color: BASE_COLOR }] : []),
  ];

  return (
    <Panel>
      <View style={styles.panelContent}>
        <View style={styles.chartContainer}>
          <View style={styles.chartWrapper}>
            <PieChart
              data={chartData}
              donut
              innerRadius={PIE_SIZE * 0.3}
              radius={PIE_SIZE * 0.5}
              innerCircleColor={theme.colors.surface.base}
              centerLabelComponent={() => (
                <View style={styles.centerLabel}>
                  <Text style={styles.totalValue}>{formatDisplayCurrency(totalMarketValue)}</Text>
                  <Text style={styles.totalLabel}>By Chain</Text>
                </View>
              )}
            />
          </View>
        </View>

        <View style={styles.legendList}>
          {hasEth && (
            <View style={styles.legendRow}>
              <View style={[styles.colorDot, { backgroundColor: ETH_COLOR }]} />
              <Text style={styles.chainName}>Ethereum</Text>
              <View style={styles.rightGroup}>
                <Text style={styles.cryptoBalance}>{formatCryptoBalance(totals.eth, '').trimEnd()}</Text>
                <Text style={styles.marketValue}>{formatDisplayCurrency(totals.ethTotalMarketValue)}</Text>
                <Text style={styles.percentageText}>{formatPercentage(ethPercentage, 1)}</Text>
              </View>
            </View>
          )}
          {hasBtc && (
            <View style={styles.legendRow}>
              <View style={[styles.colorDot, { backgroundColor: BTC_COLOR }]} />
              <Text style={styles.chainName}>Bitcoin</Text>
              <View style={styles.rightGroup}>
                <Text style={styles.cryptoBalance}>{formatCryptoBalance(totals.btc, '').trimEnd()}</Text>
                <Text style={styles.marketValue}>{formatDisplayCurrency(totals.btcTotalMarketValue)}</Text>
                <Text style={styles.percentageText}>{formatPercentage(btcPercentage, 1)}</Text>
              </View>
            </View>
          )}
          {hasBase && (
            <View style={styles.legendRow}>
              <View style={[styles.colorDot, { backgroundColor: BASE_COLOR }]} />
              <Text style={styles.chainName}>Base</Text>
              <View style={styles.rightGroup}>
                <Text style={styles.cryptoBalance}>{formatCryptoBalance(totals.base, '').trimEnd()}</Text>
                <Text style={styles.marketValue}>{formatDisplayCurrency(totals.baseTotalMarketValue)}</Text>
                <Text style={styles.percentageText}>{formatPercentage(basePercentage, 1)}</Text>
              </View>
            </View>
          )}
        </View>
      </View>
    </Panel>
  );
}
