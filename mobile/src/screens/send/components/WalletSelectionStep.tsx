import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import {
  WalletIcon,
  CheckCircleIcon,
  ClockIcon,
  PaperPlaneTiltIcon,
  CurrencyEthIcon,
  CurrencyBtcIcon,
} from 'phosphor-react-native';
import { BLOCKCHAIN, WALLET_VERIFICATION_STATUS } from '@ledova/shared-constants';
import { formatWalletAddressShort, formatCryptoBalance, formatSyncAge } from '@ledova/shared-utils';
import type { Wallet } from '@ledova/shared-types';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useCurrency } from '../../../hooks/useCurrency';

interface WalletSelectionStepProps {
  wallets: Wallet[];
  isLoading: boolean;
  onSelectWallet: (wallet: Wallet) => void;
}

export function WalletSelectionStep({ wallets, isLoading, onSelectWallet }: WalletSelectionStepProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.xs,
      gap: theme.spacing.md,
    },
    heroSection: {
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
      paddingBottom: theme.spacing.lg,
    },
    heroSubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    centerContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: theme.spacing.lg,
      gap: theme.spacing.md,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    emptyTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      textAlign: 'center',
    },
    emptySubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    chainGroup: {
      gap: theme.spacing.xs,
    },
    divider: {
      height: 1,
      backgroundColor: theme.colors.border.subtle,
    },
    chainHeaderRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
    },
    chainHeader: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    walletRow: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: theme.spacing.sm,
      gap: theme.spacing.sm,
    },
    iconContainer: {
      position: 'relative',
    },
    verificationDot: {
      position: 'absolute',
      bottom: -2,
      right: -2,
    },
    walletName: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      flexShrink: 1,
    },
    spacer: {
      flex: 1,
    },
    valuesContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      flexShrink: 0,
    },
    syncAge: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    syncAgeText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    balance: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    marketValue: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
  }));

  if (isLoading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="small" color={theme.colors.interactive.active} />
        <Text style={styles.loadingText}>Loading wallets...</Text>
      </View>
    );
  }

  if (wallets.length === 0) {
    return (
      <View style={styles.centerContainer}>
        <WalletIcon size={theme.icon.sizes.xl} color={theme.colors.text.subtle} weight={theme.icon.weights.light} />
        <Text style={styles.emptyTitle}>No verified wallets found</Text>
        <Text style={styles.emptySubtitle}>Create and verify a wallet to send crypto</Text>
      </View>
    );
  }

  const ethWallets = wallets.filter((w) => w.chain === BLOCKCHAIN.ETHEREUM);
  const btcWallets = wallets.filter((w) => w.chain === BLOCKCHAIN.BITCOIN);

  const renderWallet = (wallet: Wallet) => {
    const walletLabel = wallet.name || formatWalletAddressShort(wallet.address);
    const isVerified = wallet.verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED;
    const marketValue = parseFloat(wallet.marketValue) || 0;
    const syncAge = formatSyncAge(wallet.lastSyncedAt);

    return (
      <TouchableOpacity
        key={wallet.uuid}
        style={styles.walletRow}
        onPress={() => onSelectWallet(wallet)}
        activeOpacity={0.7}
      >
        <View style={styles.iconContainer}>
          <WalletIcon
            size={theme.icon.sizes.md}
            color={isVerified ? theme.colors.status.success.icon : theme.colors.text.muted}
            weight={theme.icon.weights.regular}
          />
          {isVerified ? (
            <CheckCircleIcon
              size={theme.icon.sizes.xs}
              color={theme.colors.status.success.icon}
              weight="fill"
              style={styles.verificationDot}
            />
          ) : (
            <ClockIcon
              size={theme.icon.sizes.xs}
              color={theme.colors.status.warning.icon}
              weight="fill"
              style={styles.verificationDot}
            />
          )}
        </View>

        <Text style={styles.walletName} numberOfLines={1}>
          {walletLabel}
        </Text>

        <View style={styles.spacer} />

        <View style={styles.valuesContainer}>
          {syncAge && (
            <View style={styles.syncAge}>
              <ClockIcon size={theme.icon.sizes.xs} color={theme.colors.text.subtle} weight="regular" />
              <Text style={styles.syncAgeText}>{syncAge}</Text>
            </View>
          )}
          <Text style={styles.balance} numberOfLines={1}>
            {formatCryptoBalance(wallet.nativeBalance, '').trimEnd()}
          </Text>
          <Text style={styles.marketValue}>{formatDisplayCurrency(marketValue)}</Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.heroSection}>
        <PaperPlaneTiltIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
        <Text style={styles.heroSubtitle}>Select your wallet</Text>
      </View>

      {ethWallets.length > 0 && (
        <View style={styles.chainGroup}>
          <View style={styles.chainHeaderRow}>
            <CurrencyEthIcon size={theme.icon.sizes.md} color={theme.colors.text.muted} weight="bold" />
            <Text style={styles.chainHeader}>Ethereum</Text>
          </View>
          {ethWallets.map(renderWallet)}
        </View>
      )}

      {ethWallets.length > 0 && btcWallets.length > 0 && <View style={styles.divider} />}

      {btcWallets.length > 0 && (
        <View style={styles.chainGroup}>
          <View style={styles.chainHeaderRow}>
            <CurrencyBtcIcon size={theme.icon.sizes.md} color={theme.colors.text.muted} weight="bold" />
            <Text style={styles.chainHeader}>Bitcoin</Text>
          </View>
          {btcWallets.map(renderWallet)}
        </View>
      )}
    </View>
  );
}
