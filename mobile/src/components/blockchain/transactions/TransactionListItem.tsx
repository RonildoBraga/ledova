import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { ArrowUpIcon, ArrowDownIcon } from 'phosphor-react-native';
import { formatShortDate, formatTime, getBlockchainShortName, formatCryptoBalance } from '@ledova/shared';
import { useCurrency } from '../../../hooks/useCurrency';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import type { Transaction } from '@ledova/shared';

interface TransactionListItemProps {
  transaction: Transaction;
  onPress: (transaction: Transaction) => void;
}

export function TransactionListItem({ transaction, onPress }: TransactionListItemProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    container: {
      paddingVertical: theme.spacing.md,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    main: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    leftSection: {
      flexDirection: 'row',
      gap: theme.spacing.xs,
      flex: 1,
      alignItems: 'center',
    },
    assetBadge: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.secondary,
      fontWeight: theme.fontWeight.semibold,
    },
    separator: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    date: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    rightSection: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    amount: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    marketValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
  }));
  const isIncoming = (): boolean => {
    const walletAddr = transaction.walletAddress?.toLowerCase() || '';
    const toAddress = transaction.toAddress?.toLowerCase() || '';
    return toAddress === walletAddr;
  };

  const incoming = isIncoming();
  const amount = parseFloat(transaction.amount || '0');
  const marketValue = transaction.marketValue ? parseFloat(transaction.marketValue) : null;
  const chainShortName = getBlockchainShortName(transaction.assetSymbol || '');

  return (
    <TouchableOpacity
      style={styles.container}
      onPress={() => onPress(transaction)}
      activeOpacity={0.7}
      id={transaction.uuid}
    >
      <View style={styles.main}>
        <View style={styles.leftSection}>
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
          <Text style={styles.assetBadge} numberOfLines={1}>
            {chainShortName}
          </Text>
          <Text style={styles.separator}>•</Text>
          <Text style={styles.date} numberOfLines={1}>
            {formatShortDate(transaction.blockTimestamp)} {formatTime(transaction.blockTimestamp)}
          </Text>
        </View>
        <View style={styles.rightSection}>
          <Text style={styles.amount} numberOfLines={1}>
            {formatCryptoBalance(amount, chainShortName)}
          </Text>
          {marketValue !== null && (
            <Text style={styles.marketValue} numberOfLines={1}>
              {formatDisplayCurrency(marketValue)}
            </Text>
          )}
        </View>
      </View>
    </TouchableOpacity>
  );
}
