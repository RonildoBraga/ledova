import React, { useRef } from 'react';
import { Animated, Text, TouchableOpacity, View } from 'react-native';
import { Swipeable } from 'react-native-gesture-handler';
import { WalletIcon, CheckCircleIcon, ClockIcon, ArrowsClockwiseIcon, TrashIcon } from 'phosphor-react-native';

import { useAppTheme, useThemedStyles } from '../../../contexts';
import type { Wallet } from '@ledova/shared';
import {
  WALLET_VERIFICATION_STATUS,
  formatWalletAddressShort,
  formatCryptoBalance,
  formatSyncAge,
} from '@ledova/shared';
import { useCurrency } from '../../../hooks/useCurrency';

interface WalletItemProps {
  wallet: Wallet;
  onPress?: () => void;
  onSync?: () => void;
  onDelete?: () => void;
  isSyncing?: boolean;
}

export function WalletItem({ wallet, onPress, onSync, onDelete, isSyncing }: WalletItemProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const swipeableRef = useRef<Swipeable>(null);
  const styles = useThemedStyles((theme) => ({
    container: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
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
    spacer: {
      flex: 1,
    },
    label: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      flexShrink: 1,
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
    swipeAction: {
      justifyContent: 'center',
      alignItems: 'center',
      width: 64,
      borderRadius: theme.borderRadius.md,
    },
    swipeSync: {
      backgroundColor: theme.colors.interactive.active,
    },
    swipeDelete: {
      backgroundColor: theme.colors.error.default,
    },
    swipeActionLabel: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.utility.white,
      marginTop: 2,
    },
  }));
  const isVerified = wallet.verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED;
  const marketValue = parseFloat(wallet.marketValue) || 0;
  const walletName = wallet.name || formatWalletAddressShort(wallet.address);
  const syncAge = formatSyncAge(wallet.lastSyncedAt);

  const renderRightActions = (_progress: Animated.AnimatedInterpolation<number>) => {
    if (!onSync && !onDelete) return null;
    return (
      <View style={{ flexDirection: 'row', gap: theme.spacing.xs, marginLeft: theme.spacing.xs }}>
        {onSync && (
          <TouchableOpacity
            style={[styles.swipeAction, styles.swipeSync]}
            onPress={() => {
              swipeableRef.current?.close();
              onSync();
            }}
            activeOpacity={0.7}
          >
            <ArrowsClockwiseIcon size={theme.icon.sizes.md} color={theme.colors.utility.white} weight="bold" />
            <Text style={styles.swipeActionLabel}>Sync</Text>
          </TouchableOpacity>
        )}
        {onDelete && (
          <TouchableOpacity
            style={[styles.swipeAction, styles.swipeDelete]}
            onPress={() => {
              swipeableRef.current?.close();
              onDelete();
            }}
            activeOpacity={0.7}
          >
            <TrashIcon size={theme.icon.sizes.md} color={theme.colors.utility.white} weight="bold" />
            <Text style={styles.swipeActionLabel}>Delete</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  const content = (
    <>
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

      <Text style={styles.label} numberOfLines={1}>
        {walletName}
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
    </>
  );

  const walletRow = onPress ? (
    <TouchableOpacity style={styles.container} onPress={onPress} activeOpacity={0.7}>
      {content}
    </TouchableOpacity>
  ) : (
    <View style={styles.container}>{content}</View>
  );

  if (onSync || onDelete) {
    return (
      <Swipeable ref={swipeableRef} renderRightActions={renderRightActions} overshootRight={false}>
        {walletRow}
      </Swipeable>
    );
  }

  return walletRow;
}
