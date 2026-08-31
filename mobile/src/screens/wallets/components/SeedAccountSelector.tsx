import React from 'react';
import { View, Text, TouchableOpacity, ScrollView } from 'react-native';
import { WalletIcon, CheckIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { PrimaryButton, SecondaryButton } from '../../../components/buttons';
import type { DerivedAddress } from '@ledova/shared-types';
import { getBlockchainDisplayName } from '@ledova/shared-constants';

interface SeedAccountSelectorProps {
  addresses: DerivedAddress[];
  selectedAddresses: Set<string>;
  balances: Map<string, string>;
  storeError: string | null;
  onToggleAddress: (address: string) => void;
  onConfirm: () => void;
  onBack: () => void;
}

export function SeedAccountSelector({
  addresses,
  selectedAddresses,
  balances,
  storeError,
  onToggleAddress,
  onConfirm,
  onBack,
}: SeedAccountSelectorProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
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
      textAlign: 'center',
    },
    scrollView: {
      flex: 1,
    },
    accountItem: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.sm,
      marginBottom: theme.spacing.sm,
    },
    accountItemSelected: {
      borderColor: theme.colors.interactive.selected.border,
      backgroundColor: theme.colors.interactive.selected.background,
    },
    checkbox: {
      width: theme.spacing.lg,
      height: theme.spacing.lg,
      borderRadius: theme.borderRadius.sm,
      borderWidth: 2,
      borderColor: theme.colors.border.strong,
      marginRight: theme.spacing.md,
      justifyContent: 'center',
      alignItems: 'center',
    },
    checkboxSelected: {
      backgroundColor: theme.colors.interactive.default,
      borderColor: theme.colors.interactive.default,
    },
    accountInfo: {
      flex: 1,
    },
    accountHeader: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: theme.spacing.xs,
    },
    networkName: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    accountBalance: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    accountAddress: {
      fontSize: theme.fontSize.xs,
      fontFamily: 'monospace',
      color: theme.colors.text.muted,
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
      marginTop: theme.spacing.sm,
    },
    actions: {
      flexDirection: 'row',
      gap: theme.spacing.md,
      paddingVertical: theme.spacing.md,
      borderTopWidth: 1,
      borderTopColor: theme.colors.border.default,
    },
    actionButton: {
      flex: 1,
    },
  }));
  return (
    <View style={styles.container}>
      <View style={styles.heroSection}>
        <WalletIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
        <Text style={styles.heroSubtitle}>Choose which accounts to add to your wallet</Text>
      </View>

      <ScrollView showsVerticalScrollIndicator={false} style={styles.scrollView}>
        {addresses.map((addr) => {
          const isSelected = selectedAddresses.has(addr.address);
          const balance = balances.get(addr.address) || 'Loading...';
          const networkName = getBlockchainDisplayName(addr.networkType);

          return (
            <TouchableOpacity
              key={addr.address}
              style={[styles.accountItem, isSelected && styles.accountItemSelected]}
              onPress={() => onToggleAddress(addr.address)}
            >
              <View style={[styles.checkbox, isSelected && styles.checkboxSelected]}>
                {isSelected && (
                  <CheckIcon size={theme.icon.sizes.sm} color={theme.colors.utility.white} weight="bold" />
                )}
              </View>
              <View style={styles.accountInfo}>
                <View style={styles.accountHeader}>
                  <Text style={styles.networkName}>{networkName}</Text>
                  <Text style={styles.accountBalance}>{balance}</Text>
                </View>
                <Text style={styles.accountAddress}>
                  {addr.address.slice(0, 10)}...{addr.address.slice(-8)}
                </Text>
              </View>
            </TouchableOpacity>
          );
        })}

        {storeError && <Text style={styles.errorText}>{storeError}</Text>}
      </ScrollView>

      <View style={styles.actions}>
        <SecondaryButton onPress={onBack} style={styles.actionButton}>
          Back
        </SecondaryButton>
        <PrimaryButton onPress={onConfirm} disabled={selectedAddresses.size === 0} style={styles.actionButton}>
          Create Wallet
        </PrimaryButton>
      </View>
    </View>
  );
}
