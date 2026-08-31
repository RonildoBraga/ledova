import React, { useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity } from 'react-native';
import { WalletIcon, QrCodeIcon } from 'phosphor-react-native';
import { getChainConfig, getAddressPlaceholder } from '@ledova/shared-constants';
import type { CreateWallet, DerivedAddress, HardwareWalletImport, WalletType } from '@ledova/shared-types';
import type { SoftwareWalletImport } from '../../../utils/softwareWallet';
import { AnimatedQRScanner } from '../../../components/qr';
import { CustomModal } from '../../../components/modal';
import { HardwareAccountSelector } from './HardwareAccountSelector';
import { WalletTypeSelector } from './WalletTypeSelector';
import { SeedPhraseSetup } from './SeedPhraseSetup';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useAddWalletForm, FORM_STEPS } from '../useAddWalletForm';

interface AddWalletModalProps {
  visible: boolean;
  isLoading: boolean;
  userAccountUuid: string | undefined;
  preselectedChain?: 'BTC' | 'ETH' | null;
  onClose: () => void;
  onSubmit: (data: CreateWallet) => void;
  onBatchSubmit: (addresses: DerivedAddress[], importData: HardwareWalletImport) => void;
  onSoftwareWalletCreate?: (addresses: DerivedAddress[], importData: SoftwareWalletImport) => void;
}

export function AddWalletModal({
  visible,
  isLoading,
  userAccountUuid,
  preselectedChain,
  onClose,
  onSubmit,
  onBatchSubmit,
  onSoftwareWalletCreate,
}: AddWalletModalProps) {
  const theme = useAppTheme();
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
    inputGroup: {
      marginBottom: theme.spacing.lg,
    },
    inputGroupCompact: {
      marginBottom: theme.spacing.sm,
    },
    labelRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: theme.spacing.sm,
    },
    label: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    labelWithMargin: {
      marginBottom: theme.spacing.sm,
    },
    scanButton: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.xs,
      paddingHorizontal: theme.spacing.sm,
      paddingVertical: theme.spacing.xs,
    },
    scanButtonText: {
      fontSize: theme.fontSize.base,
      color: theme.colors.interactive.defaultSubtle,
      fontWeight: theme.fontWeight.medium,
    },
    scannerContainer: {
      marginBottom: theme.spacing.sm,
      alignItems: 'center',
    },
    input: {
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.lg,
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
      fontFamily: 'monospace',
    },
    inputError: {
      borderColor: theme.colors.status.error.text,
    },
    errorText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.status.error.text,
      marginTop: theme.spacing.xs,
    },
  }));
  const form = useAddWalletForm({
    userAccountUuid,
    onSubmit: (data) => {
      onSubmit(data);
    },
    onBatchSubmit: (addresses, importData) => {
      onBatchSubmit(addresses, importData);
    },
    preselectedChain,
  });

  useEffect(() => {
    if (visible) {
      form.reset();
    }
  }, [visible]);

  const handleClose = () => {
    form.reset();
    onClose();
  };

  const handleWalletTypeSelect = (type: WalletType) => {
    form.setWalletType(type);
    if (type === 'software') {
      form.setStep(FORM_STEPS.SEED_PHRASE);
    } else if (type === 'hardware') {
      form.setStep(FORM_STEPS.INPUT);
      form.setShowScannerDirect(true);
    }
  };

  const handleSoftwareWalletComplete = (addresses: DerivedAddress[], importData: SoftwareWalletImport) => {
    if (onSoftwareWalletCreate) {
      onSoftwareWalletCreate(addresses, importData);
    }
  };

  const modalProps = {
    visible,
    onClose: handleClose,
    showFooter: true,
    showCancelButton: true,
    cancelLabel: 'Close',
    onCancel: handleClose,
  } as const;

  const resolveStep = () => {
    if (form.step === FORM_STEPS.SELECT_ADDRESSES && form.scannedURString) return FORM_STEPS.SELECT_ADDRESSES;
    return form.step;
  };

  const renderContent = () => {
    switch (resolveStep()) {
      case FORM_STEPS.SELECT_TYPE:
        return (
          <CustomModal {...modalProps}>
            <WalletTypeSelector onSelect={handleWalletTypeSelect} />
          </CustomModal>
        );

      case FORM_STEPS.SEED_PHRASE:
        return (
          <SeedPhraseSetup
            visible={visible}
            onClose={handleClose}
            onComplete={handleSoftwareWalletComplete}
            onCancel={() => form.setStep(FORM_STEPS.SELECT_TYPE)}
          />
        );

      case FORM_STEPS.SELECT_ADDRESSES:
        return (
          <CustomModal {...modalProps}>
            <HardwareAccountSelector
              urString={form.scannedURString!}
              onSelectAccounts={form.handleAddressSelection}
              onCancel={form.handleBackToInput}
            />
          </CustomModal>
        );

      case FORM_STEPS.INPUT:
      default:
        return (
          <CustomModal
            {...modalProps}
            cancelLabel="Back"
            onCancel={() => form.setStep(FORM_STEPS.SELECT_TYPE)}
            confirmLabel="Add Wallet"
            onConfirm={form.handleSubmit}
            confirmLoading={isLoading}
            confirmDisabled={isLoading}
          >
            <View style={styles.heroSection}>
              <WalletIcon
                size={theme.icon.sizes.xxl}
                color={theme.colors.status.info.icon}
                weight={theme.icon.weights.light}
              />
              <Text style={styles.heroSubtitle}>
                {form.showScanner ? 'Scan your wallet QR code' : 'Enter wallet details or scan a QR code'}
              </Text>
            </View>

            <View style={[styles.inputGroup, form.showScanner && styles.inputGroupCompact]}>
              <View style={styles.labelRow}>
                <Text style={styles.label}>Wallet Address</Text>
                <TouchableOpacity style={styles.scanButton} onPress={form.toggleScanner} disabled={isLoading}>
                  <QrCodeIcon
                    size={theme.icon.sizes.md}
                    color={theme.colors.interactive.defaultSubtle}
                    weight={theme.icon.weights.regular}
                  />
                  <Text style={styles.scanButtonText}>{form.showScanner ? 'Hide Scanner' : 'Scan QR'}</Text>
                </TouchableOpacity>
              </View>

              {form.showScanner ? (
                <View style={styles.scannerContainer}>
                  <AnimatedQRScanner onComplete={form.handleQRScan} />
                </View>
              ) : (
                <>
                  <TextInput
                    style={[styles.input, form.errors.address && styles.inputError]}
                    value={form.address}
                    onChangeText={form.handleAddressChange}
                    placeholder={getAddressPlaceholder(
                      form.selectedChain ? getChainConfig(form.selectedChain)?.shortName || 'ETH' : 'ETH',
                    )}
                    placeholderTextColor={theme.colors.text.muted}
                    autoCapitalize="none"
                    autoCorrect={false}
                    editable={!isLoading}
                  />
                  {form.errors.address && <Text style={styles.errorText}>{form.errors.address}</Text>}
                </>
              )}
            </View>

            {!form.showScanner && (
              <View>
                <Text style={[styles.label, styles.labelWithMargin]}>Wallet Name (Optional)</Text>
                <TextInput
                  style={styles.input}
                  value={form.name}
                  onChangeText={form.setName}
                  placeholder="e.g., Savings, Trading, Cold Storage"
                  placeholderTextColor={theme.colors.text.muted}
                  autoCapitalize="words"
                  autoCorrect={false}
                  editable={!isLoading}
                  maxLength={100}
                />
              </View>
            )}
          </CustomModal>
        );
    }
  };

  return renderContent();
}
