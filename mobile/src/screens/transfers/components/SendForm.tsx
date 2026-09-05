import React from 'react';
import { View, Text, ActivityIndicator, TouchableOpacity, TextInput, ScrollView } from 'react-native';
import { CurrencyBtcIcon, CurrencyEthIcon, CurrencyCircleDollarIcon, QrCodeIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { formatCryptoBalance, formatWalletAddressMedium, getAddressPlaceholder, isBitcoinChain } from '@ledova/shared';
import { useCurrency } from '../../../hooks/useCurrency';
import type { TransferableAsset } from '@ledova/shared';

interface SendFormProps {
  chainShortName: string;
  walletName: string;
  walletAddress: string;
  selectedAsset: TransferableAsset | null;
  transferableAssets: TransferableAsset[];
  toAddress: string;
  amount: string;
  isLoadingHoldings: boolean;
  prepareError: string | null;
  selectAsset: (asset: TransferableAsset) => void;
  setToAddress: (address: string) => void;
  setAmount: (amount: string) => void;
  useMaxAmount: () => void;
  onOpenAddressScanner: () => void;
}

export function SendForm({
  chainShortName,
  walletName,
  walletAddress,
  selectedAsset,
  transferableAssets,
  toAddress,
  amount,
  isLoadingHoldings,
  prepareError,
  selectAsset,
  setToAddress,
  setAmount,
  useMaxAmount,
  onOpenAddressScanner,
}: SendFormProps) {
  const theme = useAppTheme();
  const { formatDisplayCurrency } = useCurrency();
  const styles = useThemedStyles((theme) => ({
    scrollContent: {
      flex: 1,
    },
    scrollContentContainer: {
      padding: theme.spacing.sm,
    },
    loadingContainer: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.sm,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    heroSection: {
      alignItems: 'center',
      gap: theme.spacing.sm,
      paddingTop: theme.spacing.sm,
      paddingBottom: theme.spacing.lg,
    },
    walletName: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    assetListCard: {
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.xs,
      marginBottom: theme.spacing.md,
    },
    assetRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    assetRowSelected: {
      backgroundColor: theme.colors.interactive.active + '10',
      borderRadius: theme.borderRadius.sm,
    },
    assetRowLast: {
      borderBottomWidth: 0,
    },
    assetRowLeft: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
    },
    assetSymbol: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    assetRowRight: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    assetBalance: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    assetSeparator: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    assetFiat: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    assetTextSelected: {
      color: theme.colors.interactive.active,
    },
    inputsCard: {
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.sm,
    },
    inputSection: {
      gap: theme.spacing.sm,
    },
    inputSeparator: {
      height: 1,
      backgroundColor: theme.colors.border.subtle,
      marginVertical: theme.spacing.sm,
    },
    inputLabel: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
    },
    labelRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    scanButton: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
    },
    scanButtonText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.semibold,
    },
    useMaxLink: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.semibold,
    },
    input: {
      backgroundColor: theme.colors.surface.raised,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.md,
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
    },
    fiatEstimate: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.active,
    },
    gasWarningText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.status.warning.text,
    },
    errorContainer: {
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      borderWidth: 1,
      borderColor: theme.colors.error.default,
      marginTop: theme.spacing.md,
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
      textAlign: 'center',
    },
  }));
  const assetSymbol = selectedAsset?.symbol || chainShortName;
  const ChainIcon = isBitcoinChain(chainShortName) ? CurrencyBtcIcon : CurrencyEthIcon;

  const getAssetIcon = (asset: TransferableAsset, selected: boolean) => {
    const color = selected ? theme.colors.interactive.active : theme.colors.text.muted;
    const weight = selected ? 'duotone' : ('regular' as const);
    if (asset.isNative) {
      const NativeIcon = isBitcoinChain(chainShortName) ? CurrencyBtcIcon : CurrencyEthIcon;
      return <NativeIcon size={theme.icon.sizes.md} color={color} weight={weight} />;
    }
    return <CurrencyCircleDollarIcon size={theme.icon.sizes.md} color={color} weight={weight} />;
  };

  const balance = selectedAsset ? parseFloat(selectedAsset.balance) : 0;
  const marketValue = selectedAsset ? parseFloat(selectedAsset.marketValue) : 0;
  const unitPrice = balance > 0 ? marketValue / balance : 0;
  const parsedAmount = parseFloat(amount) || 0;
  const fiatEstimate = parsedAmount > 0 && unitPrice > 0 ? parsedAmount * unitPrice : 0;

  if (isLoadingHoldings) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="small" color={theme.colors.interactive.active} />
        <Text style={styles.loadingText}>Loading assets...</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.scrollContent}
      contentContainerStyle={styles.scrollContentContainer}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.heroSection}>
        <ChainIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
        <Text style={styles.walletName}>{walletName || formatWalletAddressMedium(walletAddress)}</Text>
      </View>

      {transferableAssets.length > 1 ? (
        <View style={styles.assetListCard}>
          {transferableAssets.map((asset: TransferableAsset, index: number) => {
            const isSelected = selectedAsset?.uuid === asset.uuid;
            const isLast = index === transferableAssets.length - 1;
            return (
              <TouchableOpacity
                key={asset.uuid}
                style={[styles.assetRow, isSelected && styles.assetRowSelected, isLast && styles.assetRowLast]}
                onPress={() => selectAsset(asset)}
                activeOpacity={0.7}
              >
                <View style={styles.assetRowLeft}>
                  {getAssetIcon(asset, isSelected)}
                  <Text style={[styles.assetSymbol, isSelected && styles.assetTextSelected]}>{asset.symbol}</Text>
                </View>
                <View style={styles.assetRowRight}>
                  {asset.isNative && (
                    <>
                      <Text style={styles.assetBalance}>{formatCryptoBalance(asset.balance, asset.symbol)}</Text>
                      <Text style={styles.assetSeparator}>&middot;</Text>
                    </>
                  )}
                  <Text style={[styles.assetFiat, isSelected && styles.assetTextSelected]}>
                    {formatDisplayCurrency(parseFloat(asset.marketValue))}
                  </Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      ) : null}

      {selectedAsset && (
        <View style={styles.inputsCard}>
          <View style={styles.inputSection}>
            <View style={styles.labelRow}>
              <Text style={styles.inputLabel}>Destination Address</Text>
              <TouchableOpacity onPress={onOpenAddressScanner} style={styles.scanButton}>
                <QrCodeIcon
                  size={theme.icon.sizes.md}
                  color={theme.colors.interactive.active}
                  weight={theme.icon.weights.regular}
                />
                <Text style={styles.scanButtonText}>Scan QR</Text>
              </TouchableOpacity>
            </View>
            <TextInput
              style={styles.input}
              value={toAddress}
              onChangeText={setToAddress}
              placeholder={getAddressPlaceholder(chainShortName)}
              placeholderTextColor={theme.colors.text.muted}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <View style={styles.inputSeparator} />

          <View style={styles.inputSection}>
            <View style={styles.labelRow}>
              <Text style={styles.inputLabel}>Amount ({assetSymbol})</Text>
              <TouchableOpacity onPress={useMaxAmount}>
                <Text style={styles.useMaxLink}>Use Max</Text>
              </TouchableOpacity>
            </View>
            <TextInput
              style={styles.input}
              value={amount}
              onChangeText={setAmount}
              placeholder="0.0"
              placeholderTextColor={theme.colors.text.muted}
              keyboardType="decimal-pad"
            />
            {fiatEstimate > 0 && <Text style={styles.fiatEstimate}>≈ {formatDisplayCurrency(fiatEstimate)}</Text>}
            {!selectedAsset.isNative && <Text style={styles.gasWarningText}>Note: ETH is required for gas fees</Text>}
          </View>
        </View>
      )}

      {prepareError && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{prepareError}</Text>
        </View>
      )}
    </ScrollView>
  );
}
