import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import type { ShareToken } from '@ledova/shared-types';
import { formatCurrency } from '@ledova/shared-utils';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface MarketListProps {
  tokens: ShareToken[];
  selectedTokenUuid: string | null;
  onSelectToken: (uuid: string) => void;
  isLoading: boolean;
}

export function MarketList({ tokens, selectedTokenUuid, onSelectToken, isLoading }: MarketListProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
      overflow: 'hidden' as const,
    },
    header: {
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.sm + 2,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    headerTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    headerSubtitle: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    row: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.sm + 2,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle + '30',
    },
    rowSelected: {
      backgroundColor: theme.colors.interactive.selected.background,
      borderLeftWidth: 2,
      borderLeftColor: theme.colors.brand.mid,
    },
    symbolCol: {
      width: 56,
    },
    symbol: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
    },
    symbolSelected: {
      color: theme.colors.brand.light,
    },
    nameCol: {
      flex: 1,
      marginLeft: theme.spacing.xs,
    },
    name: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    priceCol: {
      marginLeft: theme.spacing.sm,
      alignItems: 'flex-end' as const,
    },
    price: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      fontVariant: ['tabular-nums'] as const,
    },
    noPrice: {
      color: theme.colors.text.subtle,
    },
    loadingContainer: {
      alignItems: 'center' as const,
      paddingVertical: theme.spacing.xl,
    },
    emptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center' as const,
      paddingVertical: theme.spacing.xl,
    },
  }));

  if (isLoading) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Market</Text>
        </View>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="small" color={theme.colors.interactive.default} />
        </View>
      </View>
    );
  }

  if (tokens.length === 0) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Market</Text>
        </View>
        <Text style={styles.emptyText}>No tokens available for trading</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Market</Text>
        <Text style={styles.headerSubtitle}>Tap a token to trade</Text>
      </View>

      {tokens.map((token) => {
        const isSelected = token.uuid === selectedTokenUuid;
        const price = token.lastPrice ? parseFloat(token.lastPrice) : null;
        const bestBid = token.bestBid ? parseFloat(token.bestBid) : null;
        const displayPrice = price ?? bestBid;

        return (
          <TouchableOpacity
            key={token.uuid}
            style={[styles.row, isSelected && styles.rowSelected]}
            onPress={() => onSelectToken(token.uuid)}
            activeOpacity={0.6}
          >
            <View style={styles.symbolCol}>
              <Text style={[styles.symbol, isSelected && styles.symbolSelected]}>{token.symbol}</Text>
            </View>
            <View style={styles.nameCol}>
              <Text style={styles.name} numberOfLines={1}>
                {token.companyName || token.name}
              </Text>
            </View>
            <View style={styles.priceCol}>
              <Text style={[styles.price, displayPrice === null && styles.noPrice]}>
                {displayPrice !== null ? formatCurrency(displayPrice) : '--'}
              </Text>
            </View>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}
