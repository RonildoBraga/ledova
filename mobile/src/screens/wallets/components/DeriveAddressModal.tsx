import React, { useState, useEffect } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { KeyIcon, CheckCircleIcon } from 'phosphor-react-native';
import { CustomModal } from '../../../components/modal';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { getBlockchainDisplayName } from '@ledova/shared';
import type { Wallet, DerivedAddress } from '@ledova/shared';
import { deriveAddressFromParentKey } from '../../../utils/keystone/bcurDecoder';

interface DeriveAddressModalProps {
  visible: boolean;
  wallet: Wallet | null;
  onConfirm: (derivedAddress: DerivedAddress) => void;
  onClose: () => void;
  isCreating?: boolean;
}

export function DeriveAddressModal({
  visible,
  wallet,
  onConfirm,
  onClose,
  isCreating = false,
}: DeriveAddressModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    headerContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
    },
    icon: {
      marginBottom: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.xs,
      textAlign: 'center',
    },
    subtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    previewContainer: {
      gap: theme.spacing.sm,
      marginTop: theme.spacing.md,
    },
    previewRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    previewLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    previewValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    addressContainer: {
      paddingVertical: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    addressValue: {
      fontSize: theme.fontSize.sm,
      fontFamily: 'monospace',
      color: theme.colors.text.primary,
      marginTop: theme.spacing.xs,
    },
    pathContainer: {
      paddingVertical: theme.spacing.sm,
    },
    pathValue: {
      fontSize: theme.fontSize.xs,
      fontFamily: 'monospace',
      color: theme.colors.text.secondary,
      marginTop: theme.spacing.xs,
    },
    infoContainer: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: theme.spacing.xs,
      backgroundColor: theme.colors.surface.tertiary,
      padding: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      marginTop: theme.spacing.sm,
    },
    infoText: {
      flex: 1,
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.secondary,
    },
    loadingContainer: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.sm,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    errorContainer: {
      backgroundColor: theme.colors.form.errorBackground,
      padding: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      marginTop: theme.spacing.md,
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
      textAlign: 'center',
    },
  }));
  const [derivedAddress, setDerivedAddress] = useState<DerivedAddress | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible && wallet?.parentPublicKey && wallet?.parentChainCode && wallet?.parentDerivationPath) {
      try {
        // Derive the next address (current index + 1)
        const nextIndex = (wallet.addressIndex ?? 0) + 1;
        const newAddress = deriveAddressFromParentKey(
          wallet.parentPublicKey,
          wallet.parentChainCode,
          wallet.parentDerivationPath,
          nextIndex,
        );
        setDerivedAddress(newAddress);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to derive address');
        setDerivedAddress(null);
      }
    } else {
      setDerivedAddress(null);
      setError(null);
    }
  }, [visible, wallet]);

  const handleConfirm = () => {
    if (derivedAddress) {
      onConfirm(derivedAddress);
    }
  };

  if (!wallet) return null;

  const networkName = getBlockchainDisplayName(derivedAddress?.networkType || 'ETH');

  return (
    <CustomModal
      visible={visible}
      onClose={onClose}
      showFooter={true}
      cancelLabel="Cancel"
      confirmLabel={isCreating ? 'Adding...' : 'Add Address'}
      onConfirm={handleConfirm}
      confirmDisabled={!derivedAddress || isCreating}
      confirmLoading={isCreating}
    >
      <View style={styles.headerContainer}>
        <KeyIcon
          size={theme.icon.sizes.xl}
          color={theme.colors.interactive.active}
          weight="regular"
          style={styles.icon}
        />
        <Text style={styles.title}>Derive New Address</Text>
        <Text style={styles.subtitle}>
          {wallet.walletType === 'software'
            ? 'Add another address from your software wallet'
            : 'Add another address from your hardware wallet'}
        </Text>
      </View>

      {error ? (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      ) : derivedAddress ? (
        <View style={styles.previewContainer}>
          <View style={styles.previewRow}>
            <Text style={styles.previewLabel}>Network</Text>
            <Text style={styles.previewValue}>{networkName}</Text>
          </View>

          <View style={styles.previewRow}>
            <Text style={styles.previewLabel}>Address Index</Text>
            <Text style={styles.previewValue}>{derivedAddress.addressIndex}</Text>
          </View>

          <View style={styles.addressContainer}>
            <Text style={styles.previewLabel}>New Address</Text>
            <Text style={styles.addressValue} numberOfLines={2}>
              {derivedAddress.address}
            </Text>
          </View>

          <View style={styles.pathContainer}>
            <Text style={styles.previewLabel}>Derivation Path</Text>
            <Text style={styles.pathValue}>{derivedAddress.derivationPath}</Text>
          </View>

          <View style={styles.infoContainer}>
            <CheckCircleIcon size={theme.icon.sizes.sm} color={theme.colors.status.info.icon} weight="fill" />
            <Text style={styles.infoText}>
              {wallet.walletType === 'software'
                ? 'This address is derived from the same recovery phrase as your existing wallet'
                : 'This address shares the same master fingerprint as your existing wallet'}
            </Text>
          </View>
        </View>
      ) : (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="small" color={theme.colors.interactive.default} />
          <Text style={styles.loadingText}>Deriving address...</Text>
        </View>
      )}
    </CustomModal>
  );
}
