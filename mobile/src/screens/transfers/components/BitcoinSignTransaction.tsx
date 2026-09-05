import React from 'react';
import { View, Text, TextInput, ScrollView } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { formatWalletAddressShort } from '@ledova/shared';
import type { TransactionData } from '@ledova/shared';

interface BitcoinSignTransactionProps {
  transactionData: TransactionData;
  signedHex: string;
  onChangeSignedHex: (value: string) => void;
  error: string | null;
}

const INSTRUCTIONS = [
  'In your own Bitcoin wallet software, build a transaction from this address that pays the amount below to the recipient at the fee rate shown.',
  'Sign it there and export the signed raw transaction as hex.',
  'Paste the signed hex below and tap Broadcast.',
];

export function BitcoinSignTransaction({
  transactionData,
  signedHex,
  onChangeSignedHex,
  error,
}: BitcoinSignTransactionProps) {
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
    intro: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      lineHeight: 20,
      marginBottom: theme.spacing.md,
    },
    summarySection: {
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.lg,
    },
    sectionTitle: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
      marginBottom: theme.spacing.xs,
    },
    summaryRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    summaryLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    summaryValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      fontFamily: 'monospace',
    },
    instructionsContainer: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.lg,
    },
    instructionRow: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: theme.spacing.sm,
    },
    instructionNumber: {
      width: 22,
      height: 22,
      borderRadius: 11,
      backgroundColor: theme.colors.interactive.active,
      alignItems: 'center',
      justifyContent: 'center',
    },
    instructionNumberText: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.utility.white,
    },
    instructionText: {
      flex: 1,
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      lineHeight: 20,
    },
    inputSection: {
      gap: theme.spacing.sm,
    },
    input: {
      backgroundColor: theme.colors.surface.raised,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.md,
      fontSize: theme.fontSize.sm,
      fontFamily: 'monospace',
      color: theme.colors.text.primary,
      minHeight: 120,
      textAlignVertical: 'top',
    },
    errorText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.status.error.text,
    },
  }));

  return (
    <ScrollView
      style={styles.scrollContent}
      contentContainerStyle={styles.scrollContentContainer}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
    >
      <Text style={styles.intro}>
        This app does not build or sign Bitcoin transactions. Sign with your own wallet software and paste the result.
      </Text>

      <View style={styles.summarySection}>
        <Text style={styles.sectionTitle}>What to sign</Text>

        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>From</Text>
          <Text style={styles.summaryValue}>{formatWalletAddressShort(transactionData.fromAddress)}</Text>
        </View>

        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>To</Text>
          <Text style={styles.summaryValue}>{formatWalletAddressShort(transactionData.toAddress)}</Text>
        </View>

        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Amount</Text>
          <Text style={styles.summaryValue}>{transactionData.amountBtc} BTC</Text>
        </View>

        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Fee Rate</Text>
          <Text style={styles.summaryValue}>{transactionData.feePerByte} sat/vB</Text>
        </View>

        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Estimated Size</Text>
          <Text style={styles.summaryValue}>{transactionData.estimatedTxSize} vB</Text>
        </View>

        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Total</Text>
          <Text style={styles.summaryValue}>{transactionData.totalCostBtc} BTC</Text>
        </View>
      </View>

      <View style={styles.instructionsContainer}>
        {INSTRUCTIONS.map((instruction, index) => (
          <View key={instruction} style={styles.instructionRow}>
            <View style={styles.instructionNumber}>
              <Text style={styles.instructionNumberText}>{index + 1}</Text>
            </View>
            <Text style={styles.instructionText}>{instruction}</Text>
          </View>
        ))}
      </View>

      <View style={styles.inputSection}>
        <Text style={styles.sectionTitle}>Signed transaction (hex)</Text>
        <TextInput
          style={styles.input}
          value={signedHex}
          onChangeText={onChangeSignedHex}
          placeholder="02000000..."
          placeholderTextColor={theme.colors.text.muted}
          multiline
          autoCapitalize="none"
          autoCorrect={false}
          spellCheck={false}
        />
        {error && <Text style={styles.errorText}>{error}</Text>}
      </View>
    </ScrollView>
  );
}
