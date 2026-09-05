import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, ActivityIndicator, ScrollView } from 'react-native';
import { FingerprintSimpleIcon, CheckCircleIcon, WarningCircleIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import type { Wallet, TransactionData } from '@ledova/shared';
import { getSeedPhrase } from '../../../services/secureKeyStorage';
import { signEthereumTransaction } from '../../../utils/softwareWallet';
import { formatWalletAddressShort } from '@ledova/shared';

interface SoftwareSignTransactionProps {
  wallet: Wallet;
  transactionData: TransactionData;
  onSignComplete: (signedTxHex: string) => void;
  signTrigger?: number;
}

type SigningState = 'ready' | 'authenticating' | 'signing' | 'success' | 'error';

export function SoftwareSignTransaction({
  wallet,
  transactionData,
  onSignComplete,
  signTrigger = 0,
}: SoftwareSignTransactionProps) {
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
    summarySection: {
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.xl,
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
    statusSection: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    statusTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      textAlign: 'center',
    },
    statusText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      lineHeight: 20,
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
      textAlign: 'center',
    },
  }));
  const [signingState, setSigningState] = useState<SigningState>('ready');
  const [error, setError] = useState<string | null>(null);

  const handleSign = useCallback(async () => {
    if (!wallet.derivationPath || !wallet.masterFingerprint) {
      setError('Missing derivation path. Cannot sign this transaction.');
      setSigningState('error');
      return;
    }

    try {
      setSigningState('authenticating');
      setError(null);

      const seedId = wallet.masterFingerprint;
      const mnemonic = await getSeedPhrase(seedId);
      if (!mnemonic) {
        setSigningState('ready');
        return;
      }

      setSigningState('signing');

      const unsignedTx = JSON.parse(transactionData.transaction);

      const txData = unsignedTx.data as string | undefined;
      const isNativeTransfer = !txData || txData === '0x' || txData === '0x00';
      if (isNativeTransfer && unsignedTx.to && transactionData.toAddress) {
        if ((unsignedTx.to as string).toLowerCase() !== transactionData.toAddress.toLowerCase()) {
          throw new Error('Transaction recipient does not match expected address');
        }
      }

      const signedTx = await signEthereumTransaction(mnemonic, wallet.derivationPath, unsignedTx);

      setSigningState('success');

      setTimeout(() => {
        onSignComplete(signedTx);
      }, 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sign transaction');
      setSigningState('error');
    }
  }, [wallet, transactionData, onSignComplete]);

  useEffect(() => {
    if (signTrigger > 0) {
      handleSign();
    }
  }, [signTrigger]);

  return (
    <ScrollView
      style={styles.scrollContent}
      contentContainerStyle={styles.scrollContentContainer}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.summarySection}>
        <Text style={styles.sectionTitle}>Transaction Summary</Text>

        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>From</Text>
          <Text style={styles.summaryValue}>{formatWalletAddressShort(transactionData.fromAddress)}</Text>
        </View>

        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>To</Text>
          <Text style={styles.summaryValue}>{formatWalletAddressShort(transactionData.toAddress)}</Text>
        </View>

        {transactionData.amountEth && (
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Amount</Text>
            <Text style={styles.summaryValue}>{transactionData.amountEth} ETH</Text>
          </View>
        )}

        {transactionData.gasCostEth && (
          <View style={styles.summaryRow}>
            <Text style={styles.summaryLabel}>Gas</Text>
            <Text style={styles.summaryValue}>{transactionData.gasCostEth} ETH</Text>
          </View>
        )}
      </View>

      <View style={styles.statusSection}>
        {signingState === 'ready' && (
          <>
            <FingerprintSimpleIcon size={theme.icon.sizes.xxl} color={theme.colors.interactive.active} weight="light" />
            <Text style={styles.statusTitle}>Ready to Sign</Text>
            <Text style={styles.statusText}>
              Tap &quot;Sign &amp; Send&quot; below to authenticate and sign this transaction with your software wallet.
            </Text>
          </>
        )}

        {(signingState === 'authenticating' || signingState === 'signing') && (
          <>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.statusTitle}>
              {signingState === 'authenticating' ? 'Authenticating...' : 'Signing Transaction...'}
            </Text>
          </>
        )}

        {signingState === 'success' && (
          <>
            <CheckCircleIcon size={theme.icon.sizes.xxl} color={theme.colors.status.success.icon} weight="light" />
            <Text style={styles.statusTitle}>Transaction Signed</Text>
          </>
        )}

        {signingState === 'error' && (
          <>
            <WarningCircleIcon size={theme.icon.sizes.xxl} color={theme.colors.status.error.icon} weight="light" />
            <Text style={styles.statusTitle}>Signing Failed</Text>
            {error && <Text style={styles.errorText}>{error}</Text>}
          </>
        )}
      </View>
    </ScrollView>
  );
}
