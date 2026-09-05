import React, { useState, useMemo } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import {
  ArrowUpIcon,
  ArrowDownIcon,
  ArrowsDownUpIcon,
  ArrowsLeftRightIcon,
  ClockIcon,
  PencilSimpleIcon,
  TrashIcon,
} from 'phosphor-react-native';
import type { TransferOrder, SwapOrder, OrderBook as OrderBookType, OrderBookEntry } from '@ledova/shared';
import { formatCurrency } from '@ledova/shared';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface OrdersCardProps {
  tokenSymbol: string;
  orderBook: OrderBookType | null;
  isLoadingOrderBook: boolean;
  userOrders: TransferOrder[];
  isLoadingUserOrders: boolean;
  onCancelOrder: (uuid: string) => void;
  onEditOrder: (order: TransferOrder) => void;
  onViewOrder: (order: TransferOrder) => void;
  swaps: SwapOrder[] | undefined;
  isLoadingSwaps: boolean;
  walletAddresses: string[];
  onSignSwap: (swap: SwapOrder) => void;
}

function getTimeAgo(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffMins < 1) return 'now';
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 7) return `${diffDays}d`;
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function formatSwapTimeRemaining(expiresAt: string): string {
  const expiry = new Date(expiresAt);
  const now = new Date();
  const ms = expiry.getTime() - now.getTime();
  if (ms <= 0) return 'Expired';
  const hours = Math.floor(ms / (1000 * 60 * 60));
  const minutes = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60));
  if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function OrderBookRow({
  entry,
  maxQuantity,
  side,
  theme,
}: {
  entry: OrderBookEntry;
  maxQuantity: number;
  side: 'ask' | 'bid';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  theme: any;
}) {
  const depthPercent = maxQuantity > 0 ? (entry.quantity / maxQuantity) * 100 : 0;
  const total = parseFloat(entry.price) * entry.quantity;
  const isAsk = side === 'ask';
  const barColor = isAsk ? theme.colors.status.error.icon + '0A' : theme.colors.status.success.icon + '0A';
  const priceColor = isAsk ? theme.colors.status.error.icon : theme.colors.status.success.icon;

  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 3,
        paddingHorizontal: theme.spacing.md,
        position: 'relative',
      }}
    >
      <View
        style={{
          position: 'absolute',
          top: 0,
          bottom: 0,
          [isAsk ? 'right' : 'left']: 0,
          width: `${Math.min(depthPercent, 100)}%`,
          backgroundColor: barColor,
        }}
      />
      <Text
        style={{
          flex: 1,
          fontSize: theme.fontSize.xs,
          fontWeight: theme.fontWeight.medium,
          color: priceColor,
          fontVariant: ['tabular-nums'],
        }}
      >
        {formatCurrency(parseFloat(entry.price))}
      </Text>
      <Text
        style={{
          width: 45,
          textAlign: 'right',
          fontSize: theme.fontSize.xs,
          color: theme.colors.text.secondary,
          fontVariant: ['tabular-nums'],
        }}
      >
        {entry.quantity.toLocaleString()}
      </Text>
      <Text
        style={{
          width: 55,
          textAlign: 'right',
          fontSize: theme.fontSize.xs,
          color: theme.colors.text.muted,
          fontVariant: ['tabular-nums'],
        }}
      >
        {formatCurrency(total)}
      </Text>
    </View>
  );
}

export function OrdersCard({
  tokenSymbol,
  orderBook,
  isLoadingOrderBook,
  userOrders,
  isLoadingUserOrders,
  onCancelOrder,
  onEditOrder,
  onViewOrder,
  swaps,
  isLoadingSwaps,
  walletAddresses,
  onSignSwap,
}: OrdersCardProps) {
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
      flexDirection: 'row' as const,
      justifyContent: 'space-between' as const,
      alignItems: 'center' as const,
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
    },
    spreadText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    spreadValue: {
      color: theme.colors.text.secondary,
      fontWeight: theme.fontWeight.medium,
    },
    bookContainer: {
      flexDirection: 'row' as const,
    },
    bookSide: {
      flex: 1,
    },
    bookDivider: {
      width: 1,
      backgroundColor: theme.colors.border.subtle,
    },
    columnHeaders: {
      flexDirection: 'row' as const,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.xs,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle + '30',
    },
    columnHeader: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    emptyBook: {
      alignItems: 'center' as const,
      justifyContent: 'center' as const,
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.sm,
    },
    emptyText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      textAlign: 'center' as const,
      paddingVertical: theme.spacing.md,
    },
    emptySubtext: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    sectionHeader: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.xs,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.xs + 2,
      backgroundColor: theme.colors.surface.tertiary + '50',
      borderTopWidth: 1,
      borderTopColor: theme.colors.border.subtle,
    },
    sectionTitle: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
    },
    orderRow: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle + '30',
    },
    orderInfo: {
      flex: 1,
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.xs,
    },
    orderSymbol: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    orderDetails: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    orderMeta: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    orderActions: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      gap: theme.spacing.xs,
    },
    actionButton: {
      padding: theme.spacing.xs,
    },
    swapRow: {
      flexDirection: 'row' as const,
      alignItems: 'center' as const,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle + '30',
      backgroundColor: theme.colors.warning.default + '08',
    },
    signButton: {
      backgroundColor: theme.colors.interactive.default,
      paddingHorizontal: theme.spacing.sm + 2,
      paddingVertical: theme.spacing.xs + 2,
      borderRadius: theme.borderRadius.md,
    },
    signButtonText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.utility.white,
    },
    roleBadge: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      paddingHorizontal: theme.spacing.xs + 2,
      paddingVertical: theme.spacing.xs / 2,
      borderRadius: theme.borderRadius.sm,
      overflow: 'hidden' as const,
    },
  }));

  const normalizedAddresses = useMemo(() => walletAddresses.map((a) => a.toLowerCase()), [walletAddresses]);

  // Order book
  const { asks, bids, maxQuantity, spread } = useMemo(() => {
    if (!orderBook)
      return {
        asks: [] as OrderBookEntry[],
        bids: [] as OrderBookEntry[],
        maxQuantity: 0,
        spread: null as string | null,
      };
    const asksSorted = [...orderBook.sellOrders].sort((a, b) => parseFloat(a.price) - parseFloat(b.price));
    const bidsSorted = [...orderBook.buyOrders].sort((a, b) => parseFloat(b.price) - parseFloat(a.price));
    const allQ = [...asksSorted, ...bidsSorted].map((e) => e.quantity);
    const max = allQ.length > 0 ? Math.max(...allQ) : 0;
    const bestAsk = asksSorted.length > 0 ? parseFloat(asksSorted[0].price) : null;
    const bestBid = bidsSorted.length > 0 ? parseFloat(bidsSorted[0].price) : null;
    const s = bestAsk !== null && bestBid !== null ? (bestAsk - bestBid).toFixed(2) : null;
    return { asks: asksSorted, bids: bidsSorted, maxQuantity: max, spread: s };
  }, [orderBook]);

  // User orders filtered to selected token
  const openOrders = userOrders.filter(
    (o) => (o.status === 'open' || o.status === 'partially_filled') && o.tokenSymbol === tokenSymbol,
  );

  const pendingSwaps = useMemo(() => {
    if (!swaps || walletAddresses.length === 0) return [];
    return swaps.filter((s) => {
      if (s.shareTokenSymbol !== tokenSymbol) return false;
      const isSeller = normalizedAddresses.includes(s.sellerAddress.toLowerCase());
      const isBuyer = normalizedAddresses.includes(s.buyerAddress.toLowerCase());
      if (!isSeller && !isBuyer) return false;
      const hasSigned = isSeller ? s.sellerHasSigned : s.buyerHasSigned;
      return !hasSigned && ['created', 'seller_signed', 'buyer_signed'].includes(s.status);
    });
  }, [swaps, walletAddresses, normalizedAddresses, tokenSymbol]);

  const hasMarketOrders = asks.length > 0 || bids.length > 0;
  const hasUserActivity = openOrders.length > 0 || pendingSwaps.length > 0;

  const handleCancelPress = (uuid: string) => {
    Alert.alert('Cancel Order', 'Are you sure you want to cancel this order?', [
      { text: 'No', style: 'cancel' },
      { text: 'Yes, Cancel', style: 'destructive', onPress: () => onCancelOrder(uuid) },
    ]);
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>{tokenSymbol} Orders</Text>
        </View>
        {spread !== null && (
          <Text style={styles.spreadText}>
            Spread <Text style={styles.spreadValue}>{formatCurrency(parseFloat(spread))}</Text>
          </Text>
        )}
      </View>

      {/* Order Book */}
      {isLoadingOrderBook ? (
        <View style={styles.emptyBook}>
          <ActivityIndicator size="small" color={theme.colors.interactive.default} />
        </View>
      ) : !hasMarketOrders ? (
        <View style={styles.emptyBook}>
          <ArrowsDownUpIcon size={theme.icon.sizes.lg} color={theme.colors.text.subtle} />
          <Text style={styles.emptyText}>No open orders for {tokenSymbol}</Text>
          <Text style={styles.emptySubtext}>Place the first order</Text>
        </View>
      ) : (
        <View style={styles.bookContainer}>
          {/* Bids */}
          <View style={styles.bookSide}>
            <View style={styles.columnHeaders}>
              <Text style={[styles.columnHeader, { flex: 1, color: theme.colors.status.success.icon }]}>Price</Text>
              <Text style={[styles.columnHeader, { width: 45, textAlign: 'right' }]}>Qty</Text>
              <Text style={[styles.columnHeader, { width: 55, textAlign: 'right' }]}>Total</Text>
            </View>
            {bids.length === 0 ? (
              <Text style={styles.emptyText}>No bids</Text>
            ) : (
              bids
                .slice(0, 5)
                .map((entry, i) => (
                  <OrderBookRow key={`bid-${i}`} entry={entry} maxQuantity={maxQuantity} side="bid" theme={theme} />
                ))
            )}
          </View>

          <View style={styles.bookDivider} />

          {/* Asks */}
          <View style={styles.bookSide}>
            <View style={styles.columnHeaders}>
              <Text style={[styles.columnHeader, { flex: 1, color: theme.colors.status.error.icon }]}>Price</Text>
              <Text style={[styles.columnHeader, { width: 45, textAlign: 'right' }]}>Qty</Text>
              <Text style={[styles.columnHeader, { width: 55, textAlign: 'right' }]}>Total</Text>
            </View>
            {asks.length === 0 ? (
              <Text style={styles.emptyText}>No asks</Text>
            ) : (
              asks
                .slice(0, 5)
                .map((entry, i) => (
                  <OrderBookRow key={`ask-${i}`} entry={entry} maxQuantity={maxQuantity} side="ask" theme={theme} />
                ))
            )}
          </View>
        </View>
      )}

      {/* Your Orders */}
      {(isLoadingUserOrders || isLoadingSwaps || hasUserActivity) && (
        <>
          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Your Orders</Text>
          </View>

          {openOrders.map((order) => {
            const isBuy = order.orderType === 'buy';
            const qty = order.remainingQuantity ?? order.quantity;
            const timeAgo = getTimeAgo(new Date(order.createdAt));

            return (
              <TouchableOpacity
                key={order.uuid}
                style={styles.orderRow}
                onPress={() => onViewOrder(order)}
                activeOpacity={0.6}
              >
                <View style={styles.orderInfo}>
                  <View
                    style={{
                      padding: theme.spacing.xs - 1,
                      borderRadius: theme.borderRadius.sm,
                      backgroundColor: isBuy
                        ? theme.colors.status.success.icon + '10'
                        : theme.colors.status.error.icon + '10',
                    }}
                  >
                    {isBuy ? (
                      <ArrowUpIcon size={theme.icon.sizes.xs} color={theme.colors.status.success.icon} weight="bold" />
                    ) : (
                      <ArrowDownIcon size={theme.icon.sizes.xs} color={theme.colors.status.error.icon} weight="bold" />
                    )}
                  </View>
                  <Text style={styles.orderDetails}>
                    {qty}@${order.pricePerShare}
                  </Text>
                  <Text style={styles.orderMeta}>{timeAgo}</Text>
                </View>
                <View style={styles.orderActions}>
                  <TouchableOpacity style={styles.actionButton} onPress={() => onEditOrder(order)}>
                    <PencilSimpleIcon size={theme.icon.sizes.sm} color={theme.colors.brand.light} />
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.actionButton} onPress={() => handleCancelPress(order.uuid)}>
                    <TrashIcon size={theme.icon.sizes.sm} color={theme.colors.status.error.icon} />
                  </TouchableOpacity>
                </View>
              </TouchableOpacity>
            );
          })}

          {pendingSwaps.map((swap) => {
            const isSeller = normalizedAddresses.includes(swap.sellerAddress.toLowerCase());
            const userRole = isSeller ? 'Seller' : 'Buyer';
            const timeRemaining = formatSwapTimeRemaining(swap.expiresAt);

            return (
              <View key={swap.uuid} style={styles.swapRow}>
                <View style={styles.orderInfo}>
                  <View
                    style={{
                      padding: theme.spacing.xs - 1,
                      borderRadius: theme.borderRadius.sm,
                      backgroundColor: theme.colors.brand.mid + '10',
                    }}
                  >
                    <ArrowsLeftRightIcon size={theme.icon.sizes.xs} color={theme.colors.brand.light} weight="bold" />
                  </View>
                  <Text style={styles.orderDetails}>{swap.shareAmount} shares</Text>
                  <Text
                    style={[
                      styles.roleBadge,
                      {
                        backgroundColor: isSeller
                          ? theme.colors.status.error.icon + '10'
                          : theme.colors.status.success.icon + '10',
                        color: isSeller ? theme.colors.status.error.icon : theme.colors.status.success.icon,
                      },
                    ]}
                  >
                    {userRole}
                  </Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                    <ClockIcon size={theme.icon.sizes.xs} color={theme.colors.text.subtle} />
                    <Text style={styles.orderMeta}>{timeRemaining}</Text>
                  </View>
                </View>
                <TouchableOpacity style={styles.signButton} onPress={() => onSignSwap(swap)}>
                  <Text style={styles.signButtonText}>Sign</Text>
                </TouchableOpacity>
              </View>
            );
          })}
        </>
      )}
    </View>
  );
}
