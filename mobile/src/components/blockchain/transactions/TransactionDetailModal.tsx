import React from 'react';
import { View, Text, Linking } from 'react-native';
import { ArrowUpIcon, ArrowDownIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import {
  formatShortDate,
  formatTime,
  formatCryptoBalance,
  getChainShortCode,
  getBlockExplorerTxUrl,
} from '@ledova/shared';
import type { Transaction } from '@ledova/shared';
import { CustomModal } from '../../modal';

interface TransactionDetailModalProps {
  visible: boolean;
  transaction: Transaction | null;
  onClose: () => void;
}

export function TransactionDetailModal({ visible, transaction, onClose }: TransactionDetailModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    headerContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
    },
    icon: {
      marginBottom: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.sm,
      textAlign: 'center',
    },
    detailsSection: {
      gap: theme.spacing.xs,
      marginTop: theme.spacing.sm,
    },
    infoRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    detailLabel: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      flex: 0,
      minWidth: 100,
    },
    detailValue: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
      fontWeight: theme.fontWeight.medium,
      flex: 1,
      textAlign: 'right',
    },
    statusSuccess: {
      color: theme.colors.status.success.text,
    },
    statusFailed: {
      color: theme.colors.status.error.text,
    },
  }));
  if (!transaction) return null;

  const isIncomingTransaction = (): boolean => {
    // Check direction from the perspective of THIS transaction's wallet
    // For internal transfers, the same tx appears twice with different wallets
    const walletAddr = transaction.walletAddress?.toLowerCase() || '';
    const toAddress = transaction.toAddress?.toLowerCase() || '';
    return toAddress === walletAddr;
  };

  const isIncoming = isIncomingTransaction();
  const amount = parseFloat(transaction.amount || '0');

  const handleOpenBlockExplorer = () => {
    const url = getBlockExplorerTxUrl(transaction.chain || '', transaction.txHash);
    Linking.openURL(url);
  };

  return (
    <CustomModal
      visible={visible}
      onClose={onClose}
      showFooter={true}
      cancelLabel="Close"
      confirmLabel="View"
      onConfirm={handleOpenBlockExplorer}
    >
      <View style={styles.headerContainer}>
        {isIncoming ? (
          <ArrowDownIcon
            size={theme.icon.sizes.xxl}
            color={theme.colors.status.success.icon}
            weight={theme.icon.weights.light}
            style={styles.icon}
          />
        ) : (
          <ArrowUpIcon
            size={theme.icon.sizes.xxl}
            color={theme.colors.status.error.icon}
            weight={theme.icon.weights.light}
            style={styles.icon}
          />
        )}
        <Text style={styles.title}>{isIncoming ? 'Received' : 'Sent'}</Text>
      </View>

      {/* Transaction Details */}
      <View style={styles.detailsSection}>
        <View style={styles.infoRow}>
          <Text style={styles.detailLabel}>Asset:</Text>
          <Text style={styles.detailValue}>{transaction.assetName || transaction.assetSymbol || 'Unknown Asset'}</Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.detailLabel}>Amount:</Text>
          <Text
            style={[
              styles.detailValue,
              { color: isIncoming ? theme.colors.status.success.icon : theme.colors.status.error.icon },
            ]}
          >
            {isIncoming ? '+' : '-'}
            {formatCryptoBalance(amount, transaction.assetSymbol || '')}
          </Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.detailLabel}>Chain:</Text>
          <Text style={styles.detailValue}>{transaction.chain ? getChainShortCode(transaction.chain) : 'Unknown'}</Text>
        </View>

        <View style={styles.infoRow}>
          <Text style={styles.detailLabel}>Timestamp:</Text>
          <Text style={styles.detailValue}>
            {formatShortDate(transaction.blockTimestamp)} {formatTime(transaction.blockTimestamp)}
          </Text>
        </View>

        {transaction.status && (
          <View style={styles.infoRow}>
            <Text style={styles.detailLabel}>Status:</Text>
            <Text
              style={[
                styles.detailValue,
                transaction.status === 'success' ? styles.statusSuccess : styles.statusFailed,
              ]}
            >
              {transaction.status === 'success' ? '✓ Success' : '✗ Failed'}
            </Text>
          </View>
        )}

        {transaction.transactionFee && (
          <View style={styles.infoRow}>
            <Text style={styles.detailLabel}>Fee:</Text>
            <Text style={styles.detailValue}>
              {formatCryptoBalance(parseFloat(transaction.transactionFee), transaction.assetSymbol || '')}
            </Text>
          </View>
        )}
      </View>
    </CustomModal>
  );
}
