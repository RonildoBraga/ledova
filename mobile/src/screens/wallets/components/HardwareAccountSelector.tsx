import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { HardDrivesIcon, CheckIcon } from 'phosphor-react-native';
import { PrimaryButton, SecondaryButton } from '../../../components/buttons';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import type { DerivedAddress, HardwareWalletImport } from '@ledova/shared';
import { extractFromKeystoneQR } from '../../../utils/keystone/bcurDecoder';
import { getBlockchainDisplayName, describeFailure, importOnEvmNetwork, importAddressKey } from '@ledova/shared';
import { useFetchBalances } from '../../../hooks/useFetchBalances';
import { WalletNetworkSelector } from './WalletNetworkSelector';

interface HardwareAccountSelectorProps {
  urString: string;
  userAccountUuid: string | undefined;
  onSelectAccounts: (addresses: DerivedAddress[], importData: HardwareWalletImport) => void;
  onCancel: () => void;
}

export function HardwareAccountSelector({
  urString,
  userAccountUuid,
  onSelectAccounts,
  onCancel,
}: HardwareAccountSelectorProps) {
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
    loadingContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
    },
    addressList: {
      flex: 1,
    },
    addressItem: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.sm,
      marginBottom: theme.spacing.sm,
    },
    addressItemSelected: {
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
    addressInfo: {
      flex: 1,
    },
    addressHeader: {
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
    addressBalance: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    addressText: {
      fontSize: theme.fontSize.xs,
      fontFamily: 'monospace',
      color: theme.colors.text.muted,
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
  const [evmNetwork, setEvmNetwork] = useState<'ETH' | 'BASE'>('ETH');
  const [selectedAddresses, setSelectedAddresses] = useState<Set<string>>(new Set());
  const [addresses, setAddresses] = useState<DerivedAddress[]>([]);
  const [importData, setImportData] = useState<HardwareWalletImport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { balances, fetchBalances } = useFetchBalances(userAccountUuid);

  useEffect(() => {
    setIsLoading(true);
    try {
      const decoded = extractFromKeystoneQR(urString);
      if (decoded) {
        const result = importOnEvmNetwork(decoded, evmNetwork);
        setAddresses(result.addresses);
        setImportData(result);
        setSelectedAddresses(new Set(result.addresses.map(importAddressKey)));
        fetchBalances(result.addresses);
      }
    } catch (error) {
      console.error(`Failed to extract QR data: ${describeFailure(error)}`);
    } finally {
      setIsLoading(false);
    }
  }, [urString, evmNetwork, fetchBalances]);

  const toggleSelection = (address: string) => {
    const newSelected = new Set(selectedAddresses);
    if (newSelected.has(address)) {
      newSelected.delete(address);
    } else {
      newSelected.add(address);
    }
    setSelectedAddresses(newSelected);
  };

  const handleImport = () => {
    if (!importData) return;
    const selected = addresses.filter((addr) => selectedAddresses.has(importAddressKey(addr)));
    onSelectAccounts(selected, importData);
  };

  if (isLoading) {
    return (
      <View style={styles.container}>
        <View style={styles.heroSection}>
          <HardDrivesIcon
            size={theme.icon.sizes.xxl}
            color={theme.colors.status.info.icon}
            weight={theme.icon.weights.light}
          />
          <Text style={styles.heroSubtitle}>Loading accounts...</Text>
        </View>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.interactive.default} />
        </View>
      </View>
    );
  }

  const renderAddressItem = (derivedAddress: DerivedAddress) => {
    const isSelected = selectedAddresses.has(importAddressKey(derivedAddress));
    const balance = balances.get(importAddressKey(derivedAddress)) || 'Loading...';
    const networkName = getBlockchainDisplayName(derivedAddress.networkType);

    return (
      <TouchableOpacity
        key={importAddressKey(derivedAddress)}
        style={[styles.addressItem, isSelected && styles.addressItemSelected]}
        onPress={() => toggleSelection(importAddressKey(derivedAddress))}
      >
        <View style={[styles.checkbox, isSelected && styles.checkboxSelected]}>
          {isSelected && (
            <CheckIcon size={theme.icon.sizes.sm} color={theme.colors.utility.white} weight={theme.icon.weights.fill} />
          )}
        </View>

        <View style={styles.addressInfo}>
          <View style={styles.addressHeader}>
            <Text style={styles.networkName}>{networkName}</Text>
            <Text style={styles.addressBalance}>{balance}</Text>
          </View>
          <Text style={styles.addressText}>
            {derivedAddress.address.slice(0, 10)}...{derivedAddress.address.slice(-8)}
          </Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.heroSection}>
        <HardDrivesIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
        <Text style={styles.heroSubtitle}>Review the accounts to import</Text>
      </View>

      {addresses.some((item) => item.networkType !== 'BTC') && (
        <WalletNetworkSelector
          evmOnly
          network={evmNetwork === 'BASE' ? 'base' : 'ethereum'}
          onChange={(network) => setEvmNetwork(network === 'base' ? 'BASE' : 'ETH')}
        />
      )}
      {!userAccountUuid && <Text style={styles.heroSubtitle}>Select an account to import wallets.</Text>}
      <ScrollView style={styles.addressList} showsVerticalScrollIndicator={false}>
        {addresses.map(renderAddressItem)}
      </ScrollView>

      <View style={styles.actions}>
        <SecondaryButton onPress={onCancel} style={styles.actionButton}>
          Cancel
        </SecondaryButton>
        <PrimaryButton
          onPress={handleImport}
          disabled={!userAccountUuid || selectedAddresses.size === 0}
          style={styles.actionButton}
        >
          Import Wallet
        </PrimaryButton>
      </View>
    </View>
  );
}
