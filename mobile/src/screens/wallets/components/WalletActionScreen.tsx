import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ActivityIndicator } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { useNavigation, useRoute } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RouteProp } from '@react-navigation/native';
import {
  ShieldCheckIcon,
  ShieldIcon,
  TreeStructureIcon,
  TrashIcon,
  FloppyDiskIcon,
  CopyIcon,
  HardDrivesIcon,
  CloudIcon,
  CurrencyBtcIcon,
  CurrencyEthIcon,
  ArrowsClockwiseIcon,
} from 'phosphor-react-native';

import type { WalletsStackParamList } from '../../../navigation/WalletsStackNavigator';
import type { Wallet, DerivedAddress } from '@ledova/shared-types';
import {
  WALLET_VERIFICATION_STATUS,
  WALLET_TYPE,
  getChainByShortName,
  getChainShortCode,
  isBitcoinChain,
} from '@ledova/shared-constants';
import { formatDate, formatCryptoBalance } from '@ledova/shared-utils';
import { useCurrency } from '../../../hooks/useCurrency';
import { GradientBackground } from '../../../components/GradientBackground';
import { Panel } from '../../../components/panel';
import { PrimaryButton } from '../../../components/buttons';
import { DeleteWalletModal } from './DeleteWalletModal';
import { DeriveAddressModal } from './DeriveAddressModal';
import { useWalletsCrud } from '../useWalletsCrud';
import { useAppTheme, useThemedStyles } from '../../../contexts';

function canDerive(wallet: Wallet, allWallets: Wallet[]): boolean {
  if (!wallet.parentPublicKey || !wallet.parentChainCode || !wallet.parentDerivationPath) return false;

  const nextIndex = (wallet.addressIndex ?? 0) + 1;
  const parentKey = `${wallet.masterFingerprint}:${wallet.parentDerivationPath}`;

  const nextExists = allWallets.some((w) => {
    if (!w.masterFingerprint || !w.parentDerivationPath) return false;
    const key = `${w.masterFingerprint}:${w.parentDerivationPath}`;
    return key === parentKey && w.addressIndex === nextIndex;
  });

  return !nextExists;
}

export function WalletActionScreen() {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    content: {
      paddingTop: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
    },
    panelContent: {
      flex: 1,
      flexDirection: 'column',
    },
    infoSection: {
      flex: 1,
      padding: theme.spacing.sm,
    },

    // Address value (copyable)
    addressValue: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'flex-end',
      gap: theme.spacing.sm,
      flex: 1,
    },

    // Hero section (market value)
    heroSection: {
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
      paddingBottom: theme.spacing.lg,
    },
    heroValue: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },

    // Detail rows
    detailsCard: {
      gap: theme.spacing.xs,
    },
    detailRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    lastDetailRow: {
      borderBottomWidth: 0,
    },
    detailLabel: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      flex: 0,
      minWidth: 100,
    },
    detailValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      flex: 1,
      textAlign: 'right',
    },

    // Type row
    typeValue: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'flex-end',
      gap: theme.spacing.xs,
    },
    typeText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    typeIconContainer: {
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.sm,
      padding: 4,
    },

    // Verification row
    verificationValue: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    verifiedText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
    },

    // Name section (at bottom of details)
    nameSection: {
      paddingHorizontal: theme.spacing.sm,
      paddingTop: theme.spacing.md,
      gap: theme.spacing.sm,
    },
    nameSectionLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    nameInput: {
      backgroundColor: theme.colors.surface.raised,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.lg,
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    nameInputDisabled: {
      opacity: 0.5,
    },
    nameHint: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },

    // Save button
    saveRow: {
      paddingHorizontal: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
    },

    // Action bar
    actionBar: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.xs,
      paddingVertical: theme.spacing.md,
      marginTop: theme.spacing.sm,
      borderTopWidth: 1,
      borderTopColor: theme.colors.border.subtle,
    },
    actionButton: {
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.xs,
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
      borderRadius: theme.borderRadius.md,
    },
    actionButtonDisabled: {
      opacity: 0.35,
    },
    actionButtonLabel: {
      fontSize: theme.fontSize.xs,
      lineHeight: 12,
      color: theme.colors.text.muted,
    },
    actionButtonLabelDisabled: {
      color: theme.colors.text.subtle,
    },
    actionButtonLabelDanger: {
      fontSize: theme.fontSize.xs,
      lineHeight: 12,
      color: theme.colors.error.light,
    },
    actionBarDivider: {
      width: 1,
      height: 32,
      backgroundColor: theme.colors.border.subtle,
      marginHorizontal: theme.spacing.xs,
    },
  }));
  const navigation = useNavigation<NativeStackNavigationProp<WalletsStackParamList>>();
  const route = useRoute<RouteProp<WalletsStackParamList, 'WalletAction'>>();
  const { wallet: routeWallet } = route.params;

  const crud = useWalletsCrud();
  const wallet = crud.wallets.find((w: Wallet) => w.uuid === routeWallet.uuid) || routeWallet;

  const isVerified = wallet.verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED;
  const marketValue = parseFloat(wallet.marketValue) || 0;
  const chainCode = getChainShortCode(wallet.chain);
  const isHardware = wallet.walletType === WALLET_TYPE.HARDWARE;
  const isBtc = isBitcoinChain(chainCode);
  const ChainIcon = isBtc ? CurrencyBtcIcon : CurrencyEthIcon;

  const [walletName, setWalletName] = useState(wallet.name || '');
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [derivingFromWallet, setDerivingFromWallet] = useState<Wallet | null>(null);

  const hasNameChanged = walletName.trim() !== (wallet.name || '');

  const handleSaveName = () => {
    if (hasNameChanged) {
      crud.updateWallet(wallet.uuid, walletName.trim(), {
        onSuccess: () => {
          if (navigation.canGoBack()) navigation.goBack();
        },
      });
    }
  };

  const canDeriveAddress = isVerified && canDerive(wallet, crud.wallets);

  const handleVerify = () => navigation.navigate('WalletVerification', { wallet });
  const handleDerive = () => setDerivingFromWallet(wallet);
  const handleDelete = () => setShowDeleteModal(true);

  const handleConfirmDelete = () => {
    crud.deleteWallet(wallet.uuid, {
      onSuccess: () => {
        setShowDeleteModal(false);
        if (navigation.canGoBack()) navigation.goBack();
      },
    });
  };

  const handleDeriveConfirm = (derivedAddress: DerivedAddress) => {
    const chain = getChainByShortName(derivedAddress.networkType);
    if (!chain) return;

    crud.createWallet(
      {
        userAccount: crud.userAccountUuid!,
        address: derivedAddress.address,
        chain: chain.code,
        walletType: wallet.walletType || 'hardware',
        derivationPath: derivedAddress.derivationPath,
        masterFingerprint: wallet.masterFingerprint,
        addressIndex: derivedAddress.addressIndex,
        parentPublicKey: wallet.parentPublicKey,
        parentChainCode: wallet.parentChainCode,
        parentDerivationPath: wallet.parentDerivationPath,
      },
      {
        onSuccess: () => {
          setDerivingFromWallet(null);
          if (navigation.canGoBack()) navigation.goBack();
        },
      },
    );
  };

  const isSyncingThis = crud.syncingWalletId === wallet.uuid;

  const handleSync = () => {
    crud.syncWallet(wallet.uuid);
  };

  const canSave = hasNameChanged && isVerified && !crud.isUpdating;

  const iconSize = theme.icon.sizes.sm;
  const disabledColor = theme.colors.text.subtle;
  const primaryIcon = (disabled: boolean) => (disabled ? disabledColor : theme.colors.utility.white);

  const displayAddress =
    wallet.address.length > 16 ? `${wallet.address.slice(0, 6)}...${wallet.address.slice(-6)}` : wallet.address;

  return (
    <GradientBackground>
      <View style={styles.container}>
        <View style={styles.content}>
          <Panel fullHeight>
            <View style={styles.panelContent}>
              <View style={styles.infoSection}>
                {/* 1. Market Value (hero) */}
                <View style={styles.heroSection}>
                  <ChainIcon
                    size={theme.icon.sizes.xxl}
                    color={theme.colors.status.info.icon}
                    weight={theme.icon.weights.light}
                  />
                  <Text style={styles.heroValue}>{formatDisplayCurrency(marketValue)}</Text>
                </View>

                {/* 2-7. Detail rows (same order as dashboard) */}
                <View style={styles.detailsCard}>
                  {/* 2. Address */}
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>Address</Text>
                    <TouchableOpacity
                      style={styles.addressValue}
                      onPress={() => Clipboard.setStringAsync(wallet.address)}
                      activeOpacity={0.7}
                    >
                      <Text style={styles.detailValue}>{displayAddress}</Text>
                      <CopyIcon
                        size={theme.icon.sizes.xs}
                        color={theme.colors.interactive.active}
                        weight={theme.icon.weights.regular}
                      />
                    </TouchableOpacity>
                  </View>

                  {/* 3. Balance */}
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>Balance</Text>
                    <Text style={styles.detailValue}>
                      {wallet.nativeBalance ? `${formatCryptoBalance(wallet.nativeBalance, chainCode)}` : 'N/A'}
                    </Text>
                  </View>

                  {/* 4. Type */}
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>Type</Text>
                    <View style={styles.typeValue}>
                      <Text style={styles.typeText}>{isHardware ? 'Hardware' : 'Software'}</Text>
                      <View style={styles.typeIconContainer}>
                        {isHardware ? (
                          <HardDrivesIcon size={theme.icon.sizes.xs} color={theme.colors.text.muted} weight="bold" />
                        ) : (
                          <CloudIcon size={theme.icon.sizes.xs} color={theme.colors.text.muted} weight="bold" />
                        )}
                      </View>
                    </View>
                  </View>

                  {/* 5. Last Sync */}
                  <View style={styles.detailRow}>
                    <Text style={styles.detailLabel}>Last Sync</Text>
                    <Text style={styles.detailValue}>{formatDate(wallet.lastSyncedAt)}</Text>
                  </View>

                  {/* 6. Verification */}
                  <View style={[styles.detailRow, styles.lastDetailRow]}>
                    <Text style={styles.detailLabel}>Verification</Text>
                    <View style={styles.verificationValue}>
                      <Text
                        style={[
                          styles.verifiedText,
                          {
                            color: isVerified ? theme.colors.status.success.text : theme.colors.status.warning.text,
                          },
                        ]}
                      >
                        {isVerified ? 'Verified' : 'Pending'}
                      </Text>
                      {isVerified ? (
                        <ShieldCheckIcon
                          size={theme.icon.sizes.sm}
                          color={theme.colors.status.success.icon}
                          weight="regular"
                        />
                      ) : (
                        <ShieldIcon
                          size={theme.icon.sizes.sm}
                          color={theme.colors.status.warning.icon}
                          weight="regular"
                        />
                      )}
                    </View>
                  </View>
                </View>

                {/* 7. Name (editable, at bottom) */}
                <View style={styles.nameSection}>
                  <Text style={styles.nameSectionLabel}>Wallet Name</Text>
                  <TextInput
                    style={[styles.nameInput, !isVerified && styles.nameInputDisabled]}
                    value={walletName}
                    onChangeText={setWalletName}
                    placeholder="Enter wallet name (optional)"
                    placeholderTextColor={theme.colors.text.subtle}
                    maxLength={30}
                    editable={isVerified && !crud.isUpdating}
                  />
                  <Text style={styles.nameHint}>Give your wallet a memorable name</Text>
                </View>
              </View>

              {/* Save button (only when name changed) */}
              {canSave && (
                <View style={styles.saveRow}>
                  <PrimaryButton
                    onPress={handleSaveName}
                    disabled={!canSave}
                    loading={crud.isUpdating}
                    size="small"
                    fullWidth
                    icon={<FloppyDiskIcon size={iconSize} color={primaryIcon(!canSave)} weight="regular" />}
                  >
                    Save Name
                  </PrimaryButton>
                </View>
              )}

              {/* Action bar (matches dashboard pattern) */}
              <View style={styles.actionBar}>
                <TouchableOpacity
                  style={[styles.actionButton, isVerified && styles.actionButtonDisabled]}
                  onPress={handleVerify}
                  disabled={isVerified}
                  activeOpacity={0.7}
                >
                  <ShieldCheckIcon
                    size={theme.icon.sizes.md}
                    color={isVerified ? disabledColor : theme.colors.text.muted}
                    weight="regular"
                  />
                  <Text style={[styles.actionButtonLabel, isVerified && styles.actionButtonLabelDisabled]}>Verify</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.actionButton, isSyncingThis && styles.actionButtonDisabled]}
                  onPress={handleSync}
                  disabled={isSyncingThis}
                  activeOpacity={0.7}
                >
                  {isSyncingThis ? (
                    <ActivityIndicator size="small" color={theme.colors.interactive.active} />
                  ) : (
                    <ArrowsClockwiseIcon size={theme.icon.sizes.md} color={theme.colors.text.muted} weight="regular" />
                  )}
                  <Text style={[styles.actionButtonLabel, isSyncingThis && styles.actionButtonLabelDisabled]}>
                    Sync
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.actionButton, !canDeriveAddress && styles.actionButtonDisabled]}
                  onPress={handleDerive}
                  disabled={!canDeriveAddress}
                  activeOpacity={0.7}
                >
                  <TreeStructureIcon
                    size={theme.icon.sizes.md}
                    color={canDeriveAddress ? theme.colors.text.muted : disabledColor}
                    weight="regular"
                  />
                  <Text style={[styles.actionButtonLabel, !canDeriveAddress && styles.actionButtonLabelDisabled]}>
                    Derive
                  </Text>
                </TouchableOpacity>

                <View style={styles.actionBarDivider} />

                <TouchableOpacity style={styles.actionButton} onPress={handleDelete} activeOpacity={0.7}>
                  <TrashIcon size={theme.icon.sizes.md} color={theme.colors.error.light} weight="regular" />
                  <Text style={styles.actionButtonLabelDanger}>Delete</Text>
                </TouchableOpacity>
              </View>
            </View>
          </Panel>
        </View>
      </View>

      <DeleteWalletModal
        visible={showDeleteModal}
        walletName={wallet.name || displayAddress}
        onConfirm={handleConfirmDelete}
        onClose={() => setShowDeleteModal(false)}
      />

      <DeriveAddressModal
        visible={!!derivingFromWallet}
        wallet={derivingFromWallet}
        onConfirm={handleDeriveConfirm}
        onClose={() => setDerivingFromWallet(null)}
        isCreating={crud.isCreating}
      />
    </GradientBackground>
  );
}
