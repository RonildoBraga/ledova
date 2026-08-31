import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity } from 'react-native';
import { LinkIcon, ArrowUpIcon, ArrowDownIcon } from 'phosphor-react-native';
import { Accordion } from '../../../components/accordion';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { formatShortDate, formatTime, getBlockchainShortName, formatCryptoBalance } from '@ledova/shared-utils';
import { useCurrency } from '../../../hooks/useCurrency';
import type { Transaction } from '@ledova/shared-types';

interface TransactionsCardProps {
  transactions: Transaction[];
  totalCount: number;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasNextPage: boolean;
  onLoadMore: () => void;
}

export function TransactionsCard({
  transactions,
  totalCount,
  isLoading,
  isLoadingMore,
  hasNextPage,
  onLoadMore,
}: TransactionsCardProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    panelContent: {
      minHeight: 100,
    },
    titleContainer: {
      flexDirection: 'row',
      alignItems: 'center',
    },
    title: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.secondary,
    },
    contentContainer: {
      gap: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
    },
    scrollContainer: {
      maxHeight: 280,
    },
    transactionsList: {
      gap: theme.spacing.xs,
    },
    transactionRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: theme.spacing.xs,
    },
    transactionLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
      flex: 1,
    },
    assetSymbol: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
    },
    separator: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    dateText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      flexShrink: 1,
    },
    transactionRight: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
    },
    cryptoAmount: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    valueSeparator: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.subtle,
    },
    marketValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    footerRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'flex-end',
      gap: theme.spacing.xs,
      paddingTop: theme.spacing.sm,
      marginTop: theme.spacing.xs,
      borderTopWidth: 1,
      borderTopColor: theme.colors.border.subtle,
    },
    footerText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    footerSeparator: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    loadMoreText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.interactive.active,
    },
    loadMoreDisabled: {
      opacity: 0.5,
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
    },
    emptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
  }));
  const isIncoming = (transaction: Transaction): boolean => {
    const walletAddr = transaction.walletAddress?.toLowerCase() || '';
    const toAddress = transaction.toAddress?.toLowerCase() || '';
    return toAddress === walletAddr;
  };

  const renderLoading = () => (
    <View style={styles.loadingContainer}>
      <ActivityIndicator size="small" color={theme.colors.interactive.active} />
      <Text style={styles.loadingText}>Loading transactions...</Text>
    </View>
  );

  const renderEmpty = () => (
    <View style={styles.emptyState}>
      <Text style={styles.emptyText}>No transactions found</Text>
    </View>
  );

  const renderTransactionRow = (transaction: Transaction, index: number) => {
    const incoming = isIncoming(transaction);
    const amount = parseFloat(transaction.amount || '0');
    const marketValue = transaction.marketValue ? parseFloat(transaction.marketValue) : null;
    const chainShortName = getBlockchainShortName(transaction.assetSymbol || '');

    return (
      <View key={transaction.uuid || index} style={styles.transactionRow}>
        <View style={styles.transactionLeft}>
          {incoming ? (
            <ArrowDownIcon
              size={theme.icon.sizes.sm}
              color={theme.colors.status.success.icon}
              weight={theme.icon.weights.light}
            />
          ) : (
            <ArrowUpIcon
              size={theme.icon.sizes.sm}
              color={theme.colors.status.error.icon}
              weight={theme.icon.weights.light}
            />
          )}
          <Text style={styles.assetSymbol}>{chainShortName}</Text>
          <Text style={styles.separator}>•</Text>
          <Text style={styles.dateText} numberOfLines={1}>
            {formatShortDate(transaction.blockTimestamp)} {formatTime(transaction.blockTimestamp)}
          </Text>
        </View>
        <View style={styles.transactionRight}>
          <Text style={styles.cryptoAmount}>{formatCryptoBalance(amount, chainShortName)}</Text>
          {marketValue !== null && (
            <>
              <Text style={styles.valueSeparator}>·</Text>
              <Text style={styles.marketValue}>{formatDisplayCurrency(marketValue)}</Text>
            </>
          )}
        </View>
      </View>
    );
  };

  const renderContent = () => (
    <View style={styles.contentContainer}>
      <ScrollView style={styles.scrollContainer} nestedScrollEnabled showsVerticalScrollIndicator={false}>
        <View style={styles.transactionsList}>
          {transactions.map((transaction, index) => renderTransactionRow(transaction, index))}
        </View>
      </ScrollView>

      <View style={styles.footerRow}>
        <Text style={styles.footerText}>
          {transactions.length} of {totalCount} transaction{totalCount !== 1 ? 's' : ''}
        </Text>
        {hasNextPage && (
          <>
            <Text style={styles.footerSeparator}>&middot;</Text>
            <TouchableOpacity onPress={onLoadMore} disabled={isLoadingMore}>
              <Text style={[styles.loadMoreText, isLoadingMore && styles.loadMoreDisabled]}>
                {isLoadingMore ? 'Loading...' : 'Load More'}
              </Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </View>
  );

  const titleContent = (
    <View style={styles.titleContainer}>
      <Text style={styles.title}>Transactions</Text>
    </View>
  );

  return (
    <Accordion title={titleContent} icon={<LinkIcon />}>
      <View style={styles.panelContent}>
        {isLoading ? renderLoading() : transactions.length === 0 ? renderEmpty() : renderContent()}
      </View>
    </Accordion>
  );
}
