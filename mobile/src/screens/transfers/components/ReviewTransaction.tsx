import React from 'react';
import { View, Text, ScrollView } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { formatWalletAddressMedium } from '@ledova/shared-utils';
import { isEthereumChain } from '@ledova/shared-constants';
import type { TransactionData } from '@ledova/shared-types';

interface ReviewTransactionProps {
  transactionData: TransactionData;
  chainShortName: string;
}

export function ReviewTransaction({ transactionData, chainShortName }: ReviewTransactionProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    scrollContent: {
      flex: 1,
    },
    scrollContentContainer: {
      paddingHorizontal: theme.spacing.md,
      paddingTop: theme.spacing.md,
      paddingBottom: theme.spacing.md,
    },
    section: {
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.lg,
    },
    sectionTitle: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
    },
    valueCard: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
    },
    addressValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      fontFamily: 'monospace',
    },
    amountValue: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    feeValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    totalCard: {
      backgroundColor: theme.colors.interactive.active + '10',
      borderColor: theme.colors.interactive.active + '30',
    },
    totalValue: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.bold,
      color: theme.colors.text.primary,
    },
    totalSubtext: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    chainDetailsCard: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
      gap: theme.spacing.sm,
    },
    chainDetailRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    chainDetailLabel: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    chainDetailValue: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
  }));
  const isEthereum = isEthereumChain(chainShortName);

  return (
    <ScrollView
      style={styles.scrollContent}
      contentContainerStyle={styles.scrollContentContainer}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>From</Text>
        <View style={styles.valueCard}>
          <Text style={styles.addressValue}>{formatWalletAddressMedium(transactionData.fromAddress)}</Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>To</Text>
        <View style={styles.valueCard}>
          <Text style={styles.addressValue}>{formatWalletAddressMedium(transactionData.toAddress)}</Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Amount</Text>
        <View style={styles.valueCard}>
          <Text style={styles.amountValue}>
            {transactionData.amountToken
              ? `${transactionData.amountToken} ${transactionData.tokenSymbol}`
              : `${transactionData.amountEth || transactionData.amountBtc} ${chainShortName}`}
          </Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Transaction Fee</Text>
        <View style={styles.valueCard}>
          <Text style={styles.feeValue}>
            {transactionData.gasCostEth || transactionData.feeBtc} {chainShortName}
          </Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Total</Text>
        <View style={[styles.valueCard, styles.totalCard]}>
          {transactionData.amountToken ? (
            <>
              <Text style={styles.totalValue}>
                {transactionData.amountToken} {transactionData.tokenSymbol}
              </Text>
              <Text style={styles.totalSubtext}>+ {transactionData.gasCostEth} ETH (gas)</Text>
            </>
          ) : (
            <Text style={styles.totalValue}>
              {transactionData.totalCostEth || transactionData.totalCostBtc} {chainShortName}
            </Text>
          )}
        </View>
      </View>

      {isEthereum && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Chain Details</Text>
          <View style={styles.chainDetailsCard}>
            <View style={styles.chainDetailRow}>
              <Text style={styles.chainDetailLabel}>Gas Price</Text>
              <Text style={styles.chainDetailValue}>{transactionData.gasPriceGwei} Gwei</Text>
            </View>
            <View style={styles.chainDetailRow}>
              <Text style={styles.chainDetailLabel}>Gas Limit</Text>
              <Text style={styles.chainDetailValue}>{transactionData.gasLimit}</Text>
            </View>
          </View>
        </View>
      )}
    </ScrollView>
  );
}
