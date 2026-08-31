import React from 'react';
import { View, Text, ScrollView, TouchableOpacity } from 'react-native';
import { ArrowUpIcon, ArrowDownIcon, PencilSimpleIcon, XCircleIcon } from 'phosphor-react-native';
import { formatWalletAddressShort, formatCurrency } from '@ledova/shared-utils';
import type { TransferOrder } from '@ledova/shared-types';
import { CustomModal } from '../../../components/modal';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface OrderDetailModalProps {
  visible: boolean;
  onClose: () => void;
  order: TransferOrder | null;
  onModify?: (order: TransferOrder) => void;
  onCancel?: (orderUuid: string) => void;
}

function getStatusDisplay(status: string, theme: ReturnType<typeof useAppTheme>): { label: string; color: string } {
  switch (status) {
    case 'open':
      return { label: 'Open', color: theme.colors.status.success.icon };
    case 'partially_filled':
      return { label: 'Partially Filled', color: theme.colors.status.warning.icon };
    case 'matched':
    case 'completed':
      return { label: 'Filled', color: theme.colors.interactive.default };
    case 'cancelled':
      return { label: 'Cancelled', color: theme.colors.text.muted };
    case 'expired':
      return { label: 'Expired', color: theme.colors.text.muted };
    default:
      return { label: status, color: theme.colors.text.muted };
  }
}

export function OrderDetailModal({ visible, onClose, order, onModify, onCancel }: OrderDetailModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.lg,
    },
    headerIcon: {
      padding: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
    },
    buyIcon: {
      backgroundColor: theme.colors.success.default + '1A',
    },
    sellIcon: {
      backgroundColor: theme.colors.error.default + '1A',
    },
    headerText: {
      flex: 1,
    },
    headerTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
    },
    buyText: {
      color: theme.colors.status.success.icon,
    },
    sellText: {
      color: theme.colors.status.error.icon,
    },
    statusRow: {
      flexDirection: 'row',
      marginTop: 4,
    },
    statusBadge: {
      paddingHorizontal: 8,
      paddingVertical: 2,
      borderRadius: theme.borderRadius.sm,
    },
    statusText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
    },
    section: {
      marginBottom: theme.spacing.md,
      gap: theme.spacing.xs,
    },
    sectionTitle: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.xs,
    },
    detailRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    detailLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    detailValue: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    detailValueBold: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    detailValueMono: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      fontFamily: 'monospace',
    },
    progressBarContainer: {
      height: 6,
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: 3,
      overflow: 'hidden',
    },
    progressBar: {
      height: '100%',
      backgroundColor: theme.colors.interactive.default,
      borderRadius: 3,
    },
    actionsSection: {
      flexDirection: 'row',
      gap: theme.spacing.sm,
      marginTop: theme.spacing.md,
    },
    actionButton: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.xs,
      paddingVertical: theme.spacing.sm + 2,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
    },
    actionButtonText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.default,
    },
    cancelButton: {
      borderColor: theme.colors.error.default + '33',
      backgroundColor: theme.colors.error.default + '0D',
    },
    cancelButtonText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.status.error.icon,
    },
  }));
  if (!order) return null;

  const isBuy = order.orderType === 'buy';
  const statusDisplay = getStatusDisplay(order.status, theme);
  const isOpen = order.status === 'open' || order.status === 'partially_filled';
  const filledQuantity = order.filledQuantity || 0;
  const remainingQuantity = order.quantity - filledQuantity;
  const totalValue = order.quantity * parseFloat(order.pricePerShare);
  const filledValue = filledQuantity * parseFloat(order.pricePerShare);

  return (
    <CustomModal visible={visible} onClose={onClose} showFooter cancelLabel="Close">
      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View style={[styles.headerIcon, isBuy ? styles.buyIcon : styles.sellIcon]}>
            {isBuy ? (
              <ArrowUpIcon size={theme.icon.sizes.lg} color={theme.colors.status.success.icon} weight="bold" />
            ) : (
              <ArrowDownIcon size={theme.icon.sizes.lg} color={theme.colors.status.error.icon} weight="bold" />
            )}
          </View>
          <View style={styles.headerText}>
            <Text style={[styles.headerTitle, isBuy ? styles.buyText : styles.sellText]}>
              {isBuy ? 'Buy' : 'Sell'} {order.tokenSymbol}
            </Text>
            <View style={styles.statusRow}>
              <View style={[styles.statusBadge, { backgroundColor: statusDisplay.color + '20' }]}>
                <Text style={[styles.statusText, { color: statusDisplay.color }]}>{statusDisplay.label}</Text>
              </View>
            </View>
          </View>
        </View>

        <View style={styles.section}>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Price per Share</Text>
            <Text style={styles.detailValue}>{formatCurrency(parseFloat(order.pricePerShare))}</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Total Quantity</Text>
            <Text style={styles.detailValue}>{order.quantity} shares</Text>
          </View>
          {order.minQuantity != null && order.minQuantity > 0 && (
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Min Fill Quantity</Text>
              <Text style={styles.detailValue}>{order.minQuantity} shares</Text>
            </View>
          )}
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Total Value</Text>
            <Text style={styles.detailValueBold}>{formatCurrency(totalValue)}</Text>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Fill Progress</Text>
          <View style={styles.progressBarContainer}>
            <View
              style={[
                styles.progressBar,
                { width: `${order.quantity > 0 ? (filledQuantity / order.quantity) * 100 : 0}%` },
              ]}
            />
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Filled</Text>
            <Text style={styles.detailValue}>
              {filledQuantity} / {order.quantity} shares
            </Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Remaining</Text>
            <Text style={styles.detailValue}>{remainingQuantity} shares</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Filled Value</Text>
            <Text style={styles.detailValue}>{formatCurrency(filledValue)}</Text>
          </View>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Details</Text>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Wallet</Text>
            <Text style={styles.detailValueMono}>{formatWalletAddressShort(order.walletAddress)}</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Order ID</Text>
            <Text style={styles.detailValueMono}>{order.uuid.slice(0, 8)}...</Text>
          </View>
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Created</Text>
            <Text style={styles.detailValue}>
              {new Date(order.createdAt).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}
            </Text>
          </View>
        </View>

        {isOpen && (
          <View style={styles.actionsSection}>
            {onModify && (
              <TouchableOpacity
                style={styles.actionButton}
                onPress={() => {
                  onClose();
                  onModify(order);
                }}
              >
                <PencilSimpleIcon size={theme.icon.sizes.md} color={theme.colors.interactive.default} />
                <Text style={styles.actionButtonText}>Modify Order</Text>
              </TouchableOpacity>
            )}
            {onCancel && (
              <TouchableOpacity
                style={[styles.actionButton, styles.cancelButton]}
                onPress={() => {
                  onClose();
                  onCancel(order.uuid);
                }}
              >
                <XCircleIcon size={theme.icon.sizes.md} color={theme.colors.status.error.icon} />
                <Text style={styles.cancelButtonText}>Cancel Order</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      </ScrollView>
    </CustomModal>
  );
}
