import React, { useState, useMemo, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView } from 'react-native';
import { ShoppingCartIcon, TagIcon, WalletIcon, ShieldWarningIcon } from 'phosphor-react-native';
import { formatWalletAddressShort, formatCurrency } from '@ledova/shared-utils';
import type { ShareToken, CreateOrderRequest, Wallet } from '@ledova/shared-types';
import type { OrderType } from '@ledova/shared-constants';
import { CustomModal } from '../../../components/modal';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface CreateOrderModalProps {
  visible: boolean;
  onClose: () => void;
  token: ShareToken;
  orderType: OrderType;
  wallets: Wallet[];
  walletsWithHoldings: { walletAddress: string; balance: string }[];
  onSubmit: (data: CreateOrderRequest) => void;
  isWalletWhitelisted: (address: string) => boolean;
  isLoadingWhitelistStatus: boolean;
}

export function CreateOrderModal({
  visible,
  onClose,
  token,
  orderType,
  wallets,
  walletsWithHoldings,
  onSubmit,
  isWalletWhitelisted,
  isLoadingWhitelistStatus,
}: CreateOrderModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    headerRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.md,
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
    headerTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
    },
    buyText: {
      color: theme.colors.status.success.icon,
    },
    sellText: {
      color: theme.colors.status.error.icon,
    },
    headerSubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    warningBox: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: theme.spacing.sm,
      padding: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.warning.default + '1A',
      borderWidth: 1,
      borderColor: theme.colors.warning.default + '33',
      marginBottom: theme.spacing.md,
    },
    warningTextContainer: {
      flex: 1,
    },
    warningTitle: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.status.warning.icon,
    },
    warningDesc: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      marginTop: 4,
    },
    detailRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: theme.spacing.sm + 2,
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
      fontWeight: theme.fontWeight.semibold,
    },
    detailValueMono: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      fontFamily: 'monospace',
    },
    detailValueHighlight: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.default,
    },
    walletSelector: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.default,
    },
    formSection: {
      marginTop: theme.spacing.md,
      gap: theme.spacing.xs,
    },
    inputLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    input: {
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.sm + 4,
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
    },
    inputHintRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    inputHint: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    useMaxButton: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.interactive.default,
    },
    emptyContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    emptyTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    emptyDesc: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
  }));
  const isBuy = orderType === 'buy';
  const [quantity, setQuantity] = useState('');
  const [minQuantity, setMinQuantity] = useState('');
  const [pricePerShare, setPricePerShare] = useState('');
  const [selectedWalletIndex, setSelectedWalletIndex] = useState(0);

  const availableWallets = useMemo(() => {
    if (!isBuy) {
      return wallets.filter((w) =>
        walletsWithHoldings.some((h) => h.walletAddress.toLowerCase() === w.address.toLowerCase()),
      );
    }
    return wallets;
  }, [wallets, walletsWithHoldings, isBuy]);

  const selectedWallet = availableWallets[selectedWalletIndex];

  const currentWalletBalance = useMemo(() => {
    if (!selectedWallet || isBuy) return undefined;
    const holding = walletsWithHoldings.find(
      (h) => h.walletAddress.toLowerCase() === selectedWallet.address.toLowerCase(),
    );
    return holding?.balance;
  }, [selectedWallet, walletsWithHoldings, isBuy]);

  const totalValue = useMemo(() => {
    const qty = parseFloat(quantity) || 0;
    const price = parseFloat(pricePerShare) || 0;
    return qty * price;
  }, [quantity, pricePerShare]);

  const isValid = useMemo(() => {
    const qty = parseFloat(quantity) || 0;
    const minQty = parseFloat(minQuantity) || 0;
    const price = parseFloat(pricePerShare) || 0;

    if (qty <= 0 || price <= 0 || !selectedWallet) return false;
    if (minQty > qty) return false;
    if (!isBuy && currentWalletBalance) {
      if (qty > parseInt(currentWalletBalance, 10)) return false;
    }
    return true;
  }, [quantity, minQuantity, pricePerShare, selectedWallet, isBuy, currentWalletBalance]);

  const walletIsWhitelisted = selectedWallet ? isWalletWhitelisted(selectedWallet.address) : false;
  const isConfirmDisabled = !isValid || (!walletIsWhitelisted && !isLoadingWhitelistStatus);

  useEffect(() => {
    if (visible) {
      setQuantity('');
      setMinQuantity('');
      setPricePerShare(token.lastPrice || '');
      setSelectedWalletIndex(0);
    }
  }, [visible, token.lastPrice]);

  const handleSubmit = () => {
    if (!isValid || !selectedWallet) return;
    const minQty = parseFloat(minQuantity) || 0;
    onSubmit({
      token: token.uuid,
      orderType,
      walletUuid: selectedWallet.uuid,
      walletAddress: selectedWallet.address,
      quantity: parseFloat(quantity),
      minQuantity: minQty > 0 ? minQty : undefined,
      pricePerShare,
    });
  };

  if (wallets.length === 0) {
    return (
      <CustomModal visible={visible} onClose={onClose} showFooter cancelLabel="Close">
        <View style={styles.emptyContainer}>
          <WalletIcon size={theme.icon.sizes.xl} color={theme.colors.status.warning.icon} />
          <Text style={styles.emptyTitle}>No Wallets Found</Text>
          <Text style={styles.emptyDesc}>Please add an Ethereum wallet to your account before trading.</Text>
        </View>
      </CustomModal>
    );
  }

  if (!isBuy && availableWallets.length === 0) {
    return (
      <CustomModal visible={visible} onClose={onClose} showFooter cancelLabel="Close">
        <View style={styles.emptyContainer}>
          <WalletIcon size={theme.icon.sizes.xl} color={theme.colors.status.warning.icon} />
          <Text style={styles.emptyTitle}>No Holdings Found</Text>
          <Text style={styles.emptyDesc}>You don&apos;t have any {token.symbol} tokens in your wallets to sell.</Text>
        </View>
      </CustomModal>
    );
  }

  return (
    <CustomModal
      visible={visible}
      onClose={onClose}
      showFooter
      confirmLabel={isBuy ? 'Buy' : 'Sell'}
      onConfirm={handleSubmit}
      confirmDisabled={isConfirmDisabled}
    >
      <ScrollView showsVerticalScrollIndicator={false}>
        <View style={styles.headerRow}>
          <View style={[styles.headerIcon, isBuy ? styles.buyIcon : styles.sellIcon]}>
            {isBuy ? (
              <ShoppingCartIcon size={theme.icon.sizes.md} color={theme.colors.status.success.icon} weight="bold" />
            ) : (
              <TagIcon size={theme.icon.sizes.md} color={theme.colors.status.error.icon} weight="bold" />
            )}
          </View>
          <View>
            <Text style={[styles.headerTitle, isBuy ? styles.buyText : styles.sellText]}>
              {isBuy ? 'Buy' : 'Sell'} {token.symbol}
            </Text>
            <Text style={styles.headerSubtitle}>{token.name}</Text>
          </View>
        </View>

        {!isLoadingWhitelistStatus && selectedWallet && !walletIsWhitelisted && (
          <View style={styles.warningBox}>
            <ShieldWarningIcon size={theme.icon.sizes.md} color={theme.colors.status.warning.icon} />
            <View style={styles.warningTextContainer}>
              <Text style={styles.warningTitle}>Wallet Not Verified</Text>
              <Text style={styles.warningDesc}>
                Your wallet is not verified for trading. Complete KYC verification before placing orders.
              </Text>
            </View>
          </View>
        )}

        {token.lastPrice && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Last Price</Text>
            <Text style={styles.detailValue}>{formatCurrency(parseFloat(token.lastPrice))}</Text>
          </View>
        )}

        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>{isBuy ? 'Delivery Wallet' : 'Source Wallet'}</Text>
          {availableWallets.length === 1 ? (
            <Text style={styles.detailValueMono}>{formatWalletAddressShort(availableWallets[0].address)}</Text>
          ) : (
            <TouchableOpacity onPress={() => setSelectedWalletIndex((i) => (i + 1) % availableWallets.length)}>
              <Text style={styles.walletSelector}>
                {selectedWallet?.name || formatWalletAddressShort(selectedWallet?.address || '')} ▼
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {!isBuy && currentWalletBalance && (
          <View style={styles.detailRow}>
            <Text style={styles.detailLabel}>Available</Text>
            <Text style={styles.detailValueHighlight}>{currentWalletBalance} shares</Text>
          </View>
        )}

        <View style={styles.detailRow}>
          <Text style={styles.detailLabel}>Total Value</Text>
          <Text style={[styles.detailValue, totalValue > 0 && styles.detailValueBold]}>
            {formatCurrency(totalValue)}
          </Text>
        </View>

        <View style={styles.formSection}>
          <Text style={styles.inputLabel}>Quantity (shares)</Text>
          <TextInput
            style={styles.input}
            value={quantity}
            onChangeText={setQuantity}
            placeholder="Enter number of shares"
            placeholderTextColor={theme.colors.text.muted}
            keyboardType="numeric"
          />
          {!isBuy && currentWalletBalance && (
            <View style={styles.inputHintRow}>
              <Text style={styles.inputHint}>Max: {currentWalletBalance}</Text>
              <TouchableOpacity onPress={() => setQuantity(currentWalletBalance)}>
                <Text style={styles.useMaxButton}>Use Max</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        <View style={styles.formSection}>
          <Text style={styles.inputLabel}>Minimum Fill Quantity (optional)</Text>
          <TextInput
            style={styles.input}
            value={minQuantity}
            onChangeText={setMinQuantity}
            placeholder="0 = accept any partial fill"
            placeholderTextColor={theme.colors.text.muted}
            keyboardType="numeric"
          />
        </View>

        <View style={styles.formSection}>
          <Text style={styles.inputLabel}>Price per Share (AUD)</Text>
          <TextInput
            style={styles.input}
            value={pricePerShare}
            onChangeText={setPricePerShare}
            placeholder="Enter price per share"
            placeholderTextColor={theme.colors.text.muted}
            keyboardType="decimal-pad"
          />
          {token.lastPrice && (
            <Text style={styles.inputHint}>Last traded at {formatCurrency(parseFloat(token.lastPrice))}</Text>
          )}
        </View>
      </ScrollView>
    </CustomModal>
  );
}
