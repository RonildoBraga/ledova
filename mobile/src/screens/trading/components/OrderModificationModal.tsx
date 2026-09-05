import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { View, Text, TextInput, ActivityIndicator, ScrollView } from 'react-native';
import { CheckCircleIcon, WarningCircleIcon } from 'phosphor-react-native';
import { formatCurrency, getWalletVerificationEvmChainId } from '@ledova/shared';
import type { TransferOrder, Wallet } from '@ledova/shared';
import { CustomModal } from '../../../components/modal';
import { QRDisplay, QRScanner } from '../../../components/qr';
import { encodeEthereumMessage } from '../../../utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '../../../utils/keystone/urDecoder';
import { getSeedPhrase } from '../../../services/secureKeyStorage';
import { signEthereumMessage } from '../../../utils/softwareWallet/localSigner';
import {
  useOrderModificationMessage,
  useExecuteOrderModification,
  parseTradingError,
  type OrderModificationRequest,
  type OrderModificationMessageResponse,
} from '../useTrading';
import { useAppTheme, useThemedStyles } from '../../../contexts';

type ModificationStep =
  | 'form'
  | 'loading'
  | 'instructions'
  | 'show-qr'
  | 'signing-software'
  | 'scan-signature'
  | 'submitting'
  | 'success'
  | 'error';

interface OrderModificationModalProps {
  visible: boolean;
  onClose: () => void;
  order: TransferOrder | null;
  wallet: Wallet | null;
  onSuccess?: () => void;
}

export function OrderModificationModal({ visible, onClose, order, wallet, onSuccess }: OrderModificationModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    centeredContainer: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    contentContainer: {
      gap: theme.spacing.md,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    description: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      lineHeight: 20,
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
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
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
    inputHint: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
    },
    summaryBox: {
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      gap: theme.spacing.sm,
    },
    summaryRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    summaryLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    summaryValue: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    successTitle: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.status.success.icon,
    },
    successDesc: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    errorTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    errorDesc: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
  }));
  const [newQuantity, setNewQuantity] = useState('');
  const [newMinQuantity, setNewMinQuantity] = useState('');
  const [newPricePerShare, setNewPricePerShare] = useState('');
  const [step, setStep] = useState<ModificationStep>('form');
  const [messageData, setMessageData] = useState<OrderModificationMessageResponse | null>(null);
  const [qrData, setQrData] = useState<{ cborHex: string; type: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const modificationMessageMutation = useOrderModificationMessage();
  const executeModificationMutation = useExecuteOrderModification();

  const isSoftwareWallet = wallet?.walletType === 'software';

  useEffect(() => {
    if (visible && order) {
      setNewQuantity(order.quantity.toString());
      setNewMinQuantity(order.minQuantity?.toString() || '0');
      setNewPricePerShare(order.pricePerShare);
      setStep('form');
      setMessageData(null);
      setQrData(null);
      setError(null);
    }
  }, [visible, order]);

  const orderDetails = useMemo(() => {
    if (!order) return null;
    const filledQuantity = order.filledQuantity || 0;
    return { filledQuantity, remainingQuantity: order.quantity - filledQuantity };
  }, [order]);

  const formValidation = useMemo(() => {
    if (!order || !orderDetails) return { isValid: false, hasChanges: false };
    const qty = parseInt(newQuantity, 10) || 0;
    const minQty = parseInt(newMinQuantity, 10) || 0;
    const price = parseFloat(newPricePerShare) || 0;

    if (qty <= orderDetails.filledQuantity) return { isValid: false, hasChanges: true };
    const newRemaining = qty - orderDetails.filledQuantity;
    if (minQty > newRemaining || minQty < 0 || price <= 0) return { isValid: false, hasChanges: true };

    const hasChanges =
      qty !== order.quantity || minQty !== (order.minQuantity || 0) || price !== parseFloat(order.pricePerShare);
    return { isValid: hasChanges, hasChanges };
  }, [order, orderDetails, newQuantity, newMinQuantity, newPricePerShare]);

  const handleFormSubmit = useCallback(() => {
    if (!order || !formValidation.isValid) return;
    setStep('loading');
    setError(null);

    const modifications: OrderModificationRequest = {};
    const qty = parseInt(newQuantity, 10);
    if (qty !== order.quantity) modifications.newQuantity = qty;
    const minQty = parseInt(newMinQuantity, 10);
    if (minQty !== (order.minQuantity || 0)) modifications.newMinQuantity = minQty;
    const price = parseFloat(newPricePerShare);
    if (price !== parseFloat(order.pricePerShare)) modifications.newPricePerShare = newPricePerShare;

    modificationMessageMutation.mutate(
      { orderUuid: order.uuid, modifications },
      {
        onSuccess: (data) => {
          setMessageData(data);
          setStep('instructions');
        },
        onError: (err) => {
          setError(parseTradingError(err));
          setStep('error');
        },
      },
    );
  }, [order, formValidation.isValid, newQuantity, newMinQuantity, newPricePerShare, modificationMessageMutation]);

  const generateQrCode = useCallback(() => {
    if (!messageData || !wallet) {
      setError('Missing data');
      setStep('error');
      return;
    }
    const encoded = encodeEthereumMessage(
      wallet.address,
      messageData.message,
      wallet.derivationPath || undefined,
      wallet.masterFingerprint || undefined,
      getWalletVerificationEvmChainId(wallet.chain) ?? undefined,
    );
    if (!encoded) {
      setError('Failed to encode message');
      setStep('error');
      return;
    }
    setQrData({ cborHex: encoded.cbor.toString('hex'), type: encoded.type });
    setStep('show-qr');
  }, [messageData, wallet]);

  const handleSignatureScanned = useCallback(
    (signature: string) => {
      if (!messageData || !order) return;
      setStep('submitting');
      executeModificationMutation.mutate(
        { orderUuid: order.uuid, data: { message: messageData.message, signature } },
        {
          onSuccess: () => {
            setStep('success');
            onSuccess?.();
          },
          onError: (err) => {
            setError(parseTradingError(err));
            setStep('error');
          },
        },
      );
    },
    [messageData, order, executeModificationMutation, onSuccess],
  );

  const handleSoftwareSigning = useCallback(async () => {
    if (!messageData || !wallet?.derivationPath || !wallet?.masterFingerprint) {
      setError('Missing data');
      setStep('error');
      return;
    }
    setStep('signing-software');
    setError(null);
    try {
      const mnemonic = await getSeedPhrase(wallet.masterFingerprint);
      if (!mnemonic) {
        setStep('instructions');
        return;
      }
      const signature = await signEthereumMessage(mnemonic, wallet.derivationPath, messageData.message);
      handleSignatureScanned(signature);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sign');
      setStep('error');
    }
  }, [messageData, wallet, handleSignatureScanned]);

  const handleClose = () => {
    if (step === 'submitting') return;
    onClose();
  };

  useEffect(() => {
    if (step === 'success') {
      const timer = setTimeout(() => handleClose(), 2000);
      return () => clearTimeout(timer);
    }
  }, [step]);

  const goBack = () => {
    if (step === 'scan-signature') setStep('show-qr');
    else if (step === 'show-qr') setStep('instructions');
    else if (step === 'instructions') setStep('form');
    else if (step === 'error') {
      setStep('form');
      setError(null);
    }
  };

  const getConfirmLabel = (): string | undefined => {
    switch (step) {
      case 'form':
        return 'Continue';
      case 'instructions':
        return isSoftwareWallet ? 'Sign with Biometric' : 'Show QR Code';
      case 'show-qr':
        return "I've Signed It";
      default:
        return undefined;
    }
  };

  const handleConfirm = () => {
    switch (step) {
      case 'form':
        handleFormSubmit();
        break;
      case 'instructions':
        if (isSoftwareWallet) {
          handleSoftwareSigning();
        } else {
          generateQrCode();
        }
        break;
      case 'show-qr':
        setStep('scan-signature');
        break;
    }
  };

  const showConfirm = ['form', 'instructions', 'show-qr'].includes(step);
  const showCancel = !['loading', 'submitting', 'success', 'signing-software'].includes(step);

  const renderContent = () => {
    if (!order || !orderDetails) return null;
    switch (step) {
      case 'form': {
        const totalValue = (parseInt(newQuantity, 10) || 0) * (parseFloat(newPricePerShare) || 0);
        return (
          <ScrollView showsVerticalScrollIndicator={false}>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Filled</Text>
              <Text style={styles.detailValue}>{orderDetails.filledQuantity} shares</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Remaining</Text>
              <Text style={styles.detailValue}>{orderDetails.remainingQuantity} shares</Text>
            </View>
            <View style={styles.detailRow}>
              <Text style={styles.detailLabel}>Total Value</Text>
              <Text style={styles.detailValue}>{formatCurrency(totalValue)}</Text>
            </View>
            <View style={styles.formSection}>
              <Text style={styles.inputLabel}>Total Quantity (shares)</Text>
              <TextInput
                style={styles.input}
                value={newQuantity}
                onChangeText={setNewQuantity}
                keyboardType="numeric"
                placeholderTextColor={theme.colors.text.muted}
              />
              <Text style={styles.inputHint}>Must be greater than filled amount ({orderDetails.filledQuantity})</Text>
            </View>
            <View style={styles.formSection}>
              <Text style={styles.inputLabel}>Minimum Fill Quantity (optional)</Text>
              <TextInput
                style={styles.input}
                value={newMinQuantity}
                onChangeText={setNewMinQuantity}
                keyboardType="numeric"
                placeholder="0"
                placeholderTextColor={theme.colors.text.muted}
              />
            </View>
            <View style={styles.formSection}>
              <Text style={styles.inputLabel}>Price per Share (AUD)</Text>
              <TextInput
                style={styles.input}
                value={newPricePerShare}
                onChangeText={setNewPricePerShare}
                keyboardType="decimal-pad"
                placeholderTextColor={theme.colors.text.muted}
              />
            </View>
          </ScrollView>
        );
      }
      case 'loading':
        return (
          <View style={styles.centeredContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.loadingText}>Preparing modification...</Text>
          </View>
        );
      case 'instructions':
        return (
          <View style={styles.contentContainer}>
            <Text style={styles.description}>Sign this modification to authorize the changes.</Text>
            {messageData && (
              <View style={styles.summaryBox}>
                {messageData.newValues.quantity !== messageData.currentValues.quantity && (
                  <View style={styles.summaryRow}>
                    <Text style={styles.summaryLabel}>Quantity</Text>
                    <Text style={styles.summaryValue}>
                      {messageData.currentValues.quantity} → {messageData.newValues.quantity}
                    </Text>
                  </View>
                )}
                {messageData.newValues.minQuantity !== messageData.currentValues.minQuantity && (
                  <View style={styles.summaryRow}>
                    <Text style={styles.summaryLabel}>Min Qty</Text>
                    <Text style={styles.summaryValue}>
                      {messageData.currentValues.minQuantity} → {messageData.newValues.minQuantity}
                    </Text>
                  </View>
                )}
                {messageData.newValues.pricePerShare !== messageData.currentValues.pricePerShare && (
                  <View style={styles.summaryRow}>
                    <Text style={styles.summaryLabel}>Price</Text>
                    <Text style={styles.summaryValue}>
                      ${messageData.currentValues.pricePerShare} → ${messageData.newValues.pricePerShare}
                    </Text>
                  </View>
                )}
              </View>
            )}
          </View>
        );
      case 'show-qr':
        return (
          <View style={styles.contentContainer}>
            <Text style={styles.description}>
              Scan this QR code with your hardware wallet to sign the modification.
            </Text>
            {qrData && <QRDisplay data={qrData.cborHex} isUR />}
          </View>
        );
      case 'signing-software':
        return (
          <View style={styles.centeredContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.loadingText}>Signing modification...</Text>
          </View>
        );
      case 'submitting':
        return (
          <View style={styles.centeredContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.loadingText}>Applying modification...</Text>
          </View>
        );
      case 'success':
        return (
          <View style={styles.centeredContainer}>
            <CheckCircleIcon size={theme.icon.sizes.hero} color={theme.colors.status.success.icon} weight="fill" />
            <Text style={styles.successTitle}>Order Modified!</Text>
            <Text style={styles.successDesc}>Your order has been updated successfully.</Text>
          </View>
        );
      case 'error':
        return (
          <View style={styles.centeredContainer}>
            <WarningCircleIcon size={theme.icon.sizes.hero} color={theme.colors.status.error.icon} weight="fill" />
            <Text style={styles.errorTitle}>Modification Failed</Text>
            <Text style={styles.errorDesc}>{error || 'An error occurred'}</Text>
          </View>
        );
      default:
        return null;
    }
  };

  return (
    <>
      <CustomModal
        visible={visible && step !== 'scan-signature'}
        onClose={handleClose}
        showFooter={showConfirm || showCancel}
        showCancelButton={showCancel}
        cancelLabel={['show-qr', 'instructions', 'error'].includes(step) ? 'Back' : 'Cancel'}
        onCancel={['show-qr', 'instructions', 'error'].includes(step) ? goBack : handleClose}
        confirmLabel={getConfirmLabel()}
        onConfirm={showConfirm ? handleConfirm : undefined}
        confirmDisabled={step === 'form' && !formValidation.isValid}
      >
        {renderContent()}
      </CustomModal>

      <QRScanner
        visible={visible && step === 'scan-signature'}
        onClose={goBack}
        onScan={(data) => {
          const decoded = decodeKeystoneMessageSignature(data);
          if (decoded) handleSignatureScanned(decoded);
        }}
        title="Scan Signature"
        subtitle="Point your camera at the signature QR code on your hardware wallet."
      />
    </>
  );
}
