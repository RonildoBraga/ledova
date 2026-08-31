import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import {
  CurrencyCircleDollarIcon,
  CurrencyEthIcon,
  CurrencyBtcIcon,
  WalletIcon,
  HardDrivesIcon,
  CloudIcon,
  CheckCircleIcon,
  ClockIcon,
  WarningCircleIcon,
  ArrowRightIcon,
} from 'phosphor-react-native';
import { useQuery, useMutation } from '@tanstack/react-query';
import { BUYABLE_ASSETS, WALLET_TYPE, WALLET_VERIFICATION_STATUS, CACHE_TIMING } from '@ledova/shared-constants';
import type { BuyableAssetConfig } from '@ledova/shared-constants';
import { getWallets, getOnRampWidgetUrl, getUserProfiles } from '@ledova/shared-services';
import {
  formatWalletAddressShort,
  formatCryptoBalance,
  formatSyncAge,
  getUserVerificationStatus,
} from '@ledova/shared-utils';
import { useCurrency } from '../../../hooks/useCurrency';
import type { Wallet } from '@ledova/shared-types';
import { CustomModal } from '../../../components/modal';
import { apiClient } from '../../../services/apiClient';
import { useAppTheme, useThemedStyles } from '../../../contexts';

function getAssetIcon(symbol: string, theme: ReturnType<typeof useAppTheme>): React.ReactNode {
  switch (symbol) {
    case 'BTC':
      return (
        <CurrencyBtcIcon
          size={theme.icon.sizes.md}
          color={theme.icon.colors.primary}
          weight={theme.icon.weights.regular}
        />
      );
    case 'ETH':
      return (
        <CurrencyEthIcon
          size={theme.icon.sizes.md}
          color={theme.icon.colors.primary}
          weight={theme.icon.weights.regular}
        />
      );
    case 'USDC':
    case 'USDT':
      return (
        <CurrencyCircleDollarIcon
          size={theme.icon.sizes.md}
          color={theme.icon.colors.primary}
          weight={theme.icon.weights.regular}
        />
      );
    default:
      return (
        <CurrencyCircleDollarIcon
          size={theme.icon.sizes.md}
          color={theme.icon.colors.primary}
          weight={theme.icon.weights.regular}
        />
      );
  }
}

interface BuyCryptoModalProps {
  visible: boolean;
  onClose: () => void;
  onNavigateToWebView: (url: string) => void;
  onNavigateToProfile: () => void;
  userAccountUuid?: string;
  initialAsset?: string;
}

export function BuyCryptoModal({
  visible,
  onClose,
  onNavigateToWebView,
  onNavigateToProfile,
  userAccountUuid,
  initialAsset,
}: BuyCryptoModalProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    heroSection: {
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
      paddingBottom: theme.spacing.lg,
    },
    heroSubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    warningBanner: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      padding: theme.spacing.sm,
      marginBottom: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      backgroundColor: `${theme.colors.status.warning.icon}15`,
      borderWidth: 1,
      borderColor: `${theme.colors.status.warning.icon}30`,
    },
    warningText: {
      flex: 1,
      fontSize: theme.fontSize.xs,
      color: theme.colors.status.warning.text,
      lineHeight: 18,
    },
    optionsContainer: {
      gap: theme.spacing.sm,
    },
    optionItem: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      backgroundColor: theme.colors.surface.tertiary,
    },
    optionLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      flex: 1,
    },
    iconContainer: {
      width: theme.icon.sizes.hero,
      height: theme.icon.sizes.hero,
      borderRadius: theme.borderRadius.full,
      backgroundColor: theme.colors.surface.raised,
      alignItems: 'center',
      justifyContent: 'center',
      marginRight: theme.spacing.md,
    },
    optionItemDisabled: {
      opacity: 0.5,
    },
    optionLabel: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    optionLabelDisabled: {
      color: theme.colors.text.muted,
    },
    walletList: {
      gap: theme.spacing.xs,
    },
    walletRow: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
      gap: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.surface.tertiary,
    },
    walletIconContainer: {
      position: 'relative',
    },
    walletVerificationDot: {
      position: 'absolute',
      bottom: -2,
      right: -2,
    },
    walletNameContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
      flexShrink: 1,
    },
    walletName: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      flexShrink: 1,
    },
    walletBadge: {
      padding: theme.spacing.xs,
      alignItems: 'center',
      justifyContent: 'center',
    },
    walletSpacer: {
      flex: 1,
    },
    walletValuesContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      flexShrink: 0,
    },
    walletSyncAge: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    walletSyncAgeText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    walletBalance: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    walletMarketValue: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.icon,
      textAlign: 'center',
      marginTop: theme.spacing.md,
    },
  }));
  const [selectedAsset, setSelectedAsset] = useState<BuyableAssetConfig | null>(null);
  const [showWalletStep, setShowWalletStep] = useState(false);

  const userProfileQuery = useQuery({
    queryKey: ['userProfiles'],
    queryFn: () => getUserProfiles(apiClient),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const isProfileLoading = userProfileQuery.isLoading;
  const userProfile = userProfileQuery.data?.data?.results?.[0] || null;
  const verificationStatus = getUserVerificationStatus(userProfile);
  const isVerified = verificationStatus.type === 'verified';

  useEffect(() => {
    if (visible && initialAsset && !selectedAsset) {
      const asset = BUYABLE_ASSETS.find((a) => a.symbol === initialAsset);
      if (asset) {
        setSelectedAsset(asset);
      }
    }
  }, [visible, initialAsset, selectedAsset]);

  const walletsQuery = useQuery({
    queryKey: [
      'wallets',
      userAccountUuid,
      { chain: selectedAsset?.chain, verification_status: 'VERIFIED', order_by: 'wallet_type' },
    ],
    queryFn: () =>
      getWallets(apiClient, {
        user_account: userAccountUuid!,
        chain: selectedAsset!.chain,
        verification_status: 'VERIFIED',
        order_by: 'wallet_type',
      }),
    enabled: !!userAccountUuid && !!selectedAsset,
  });

  const matchingWallets = walletsQuery.data?.data.results || [];
  const isLoadingWallets = walletsQuery.isLoading;

  const widgetMutation = useMutation({
    mutationFn: (wallet: Wallet) =>
      getOnRampWidgetUrl(apiClient, {
        walletUuid: wallet.uuid,
        cryptoCurrency: selectedAsset!.symbol,
      }),
    onSuccess: (response) => {
      resetAndClose();
      onNavigateToWebView(response.data.url);
    },
  });

  useEffect(() => {
    if (!selectedAsset || isLoadingWallets) return;

    if (matchingWallets.length === 1 && widgetMutation.isIdle) {
      widgetMutation.mutate(matchingWallets[0]);
    } else if (matchingWallets.length !== 1) {
      setShowWalletStep(true);
    }
  }, [selectedAsset, isLoadingWallets, matchingWallets, widgetMutation]);

  const resetAndClose = () => {
    setSelectedAsset(null);
    setShowWalletStep(false);
    widgetMutation.reset();
  };

  const handleClose = () => {
    resetAndClose();
    onClose();
  };

  const handleSelectAsset = (asset: BuyableAssetConfig) => {
    setSelectedAsset(asset);
  };

  const handleBack = () => {
    if (initialAsset) {
      handleClose();
    } else {
      resetAndClose();
    }
  };

  const handleSelectWallet = (wallet: Wallet) => {
    widgetMutation.mutate(wallet);
  };

  const isOnAssetStep = !showWalletStep;
  const isProcessingAsset = !!selectedAsset && isOnAssetStep;
  const isLoading = widgetMutation.isPending;

  return (
    <CustomModal
      visible={visible}
      onClose={handleClose}
      showFooter={true}
      showCancelButton={true}
      cancelLabel={isOnAssetStep ? 'Cancel' : 'Back'}
      onCancel={isOnAssetStep ? handleClose : handleBack}
    >
      {isOnAssetStep && (
        <>
          <View style={styles.heroSection}>
            <CurrencyCircleDollarIcon
              size={theme.icon.sizes.xxl}
              color={theme.colors.status.info.icon}
              weight={theme.icon.weights.light}
            />
            <Text style={styles.heroSubtitle}>Select an asset to purchase</Text>
          </View>

          {!isProfileLoading && !isVerified && (
            <TouchableOpacity
              style={styles.warningBanner}
              onPress={() => {
                handleClose();
                onNavigateToProfile();
              }}
              activeOpacity={0.7}
            >
              <WarningCircleIcon size={theme.icon.sizes.sm} color={theme.colors.status.warning.icon} weight="fill" />
              <Text style={styles.warningText}>
                You must verify your identity before purchasing assets. Tap here to complete verification.
              </Text>
              <ArrowRightIcon size={theme.icon.sizes.sm} color={theme.colors.status.warning.icon} />
            </TouchableOpacity>
          )}

          <View style={styles.optionsContainer}>
            {BUYABLE_ASSETS.map((asset) => {
              const isAssetProcessing = isProcessingAsset && selectedAsset?.symbol === asset.symbol;
              const isDisabled = isProfileLoading || !isVerified || isProcessingAsset;

              return (
                <TouchableOpacity
                  key={asset.symbol}
                  style={[styles.optionItem, !isVerified && styles.optionItemDisabled]}
                  onPress={() => handleSelectAsset(asset)}
                  activeOpacity={isDisabled ? 1 : 0.7}
                  disabled={isDisabled}
                >
                  <View style={styles.optionLeft}>
                    <View style={styles.iconContainer}>{getAssetIcon(asset.symbol, theme)}</View>
                    <Text style={[styles.optionLabel, !isVerified && styles.optionLabelDisabled]}>{asset.name}</Text>
                  </View>
                  {isAssetProcessing && <ActivityIndicator size="small" color={theme.colors.interactive.active} />}
                </TouchableOpacity>
              );
            })}
          </View>
        </>
      )}

      {!isOnAssetStep && matchingWallets.length === 0 && (
        <View style={styles.heroSection}>
          <WalletIcon
            size={theme.icon.sizes.xxl}
            color={theme.colors.status.info.icon}
            weight={theme.icon.weights.light}
          />
          <Text style={styles.heroSubtitle}>No verified wallets for {selectedAsset!.name}. Create one in Wallets.</Text>
        </View>
      )}

      {!isOnAssetStep && matchingWallets.length > 1 && (
        <>
          <View style={styles.heroSection}>
            <WalletIcon
              size={theme.icon.sizes.xxl}
              color={theme.colors.status.info.icon}
              weight={theme.icon.weights.light}
            />
            <Text style={styles.heroSubtitle}>Choose a wallet to receive {selectedAsset!.name}</Text>
          </View>

          <View style={styles.walletList}>
            {matchingWallets.map((wallet: Wallet) => {
              const walletLabel = wallet.name || formatWalletAddressShort(wallet.address);
              const isVerified = wallet.verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED;
              const isHardware = wallet.walletType === WALLET_TYPE.HARDWARE;
              const marketValue = parseFloat(wallet.marketValue) || 0;
              const syncAge = formatSyncAge(wallet.lastSyncedAt);
              const isSelected = isLoading && widgetMutation.variables?.uuid === wallet.uuid;

              return (
                <TouchableOpacity
                  key={wallet.uuid}
                  style={styles.walletRow}
                  onPress={() => handleSelectWallet(wallet)}
                  activeOpacity={0.7}
                  disabled={isLoading}
                >
                  <View style={styles.walletIconContainer}>
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
                        style={styles.walletVerificationDot}
                      />
                    ) : (
                      <ClockIcon
                        size={theme.icon.sizes.xs}
                        color={theme.colors.status.warning.icon}
                        weight="fill"
                        style={styles.walletVerificationDot}
                      />
                    )}
                  </View>

                  <View style={styles.walletNameContainer}>
                    <Text style={styles.walletName} numberOfLines={1}>
                      {walletLabel}
                    </Text>
                    <View style={styles.walletBadge}>
                      {isHardware ? (
                        <HardDrivesIcon size={theme.icon.sizes.xs} color={theme.colors.text.muted} weight="bold" />
                      ) : (
                        <CloudIcon size={theme.icon.sizes.xs} color={theme.colors.text.muted} weight="bold" />
                      )}
                    </View>
                  </View>

                  <View style={styles.walletSpacer} />

                  {isSelected ? (
                    <ActivityIndicator size="small" color={theme.colors.interactive.active} />
                  ) : (
                    <View style={styles.walletValuesContainer}>
                      {syncAge && (
                        <View style={styles.walletSyncAge}>
                          <ClockIcon size={theme.icon.sizes.xs} color={theme.colors.text.subtle} weight="regular" />
                          <Text style={styles.walletSyncAgeText}>{syncAge}</Text>
                        </View>
                      )}
                      <Text style={styles.walletBalance} numberOfLines={1}>
                        {formatCryptoBalance(wallet.nativeBalance, '').trimEnd()}
                      </Text>
                      <Text style={styles.walletMarketValue}>{formatDisplayCurrency(marketValue)}</Text>
                    </View>
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </>
      )}

      {(widgetMutation.isError || walletsQuery.isError) && (
        <Text style={styles.errorText}>
          {widgetMutation.error instanceof Error
            ? widgetMutation.error.message
            : walletsQuery.error instanceof Error
              ? walletsQuery.error.message
              : 'Something went wrong'}
        </Text>
      )}
    </CustomModal>
  );
}
