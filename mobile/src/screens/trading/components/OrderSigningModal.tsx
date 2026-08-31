import React, { useEffect } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { CheckCircleIcon, WarningCircleIcon } from 'phosphor-react-native';
import type { CreateOrderRequest, TransferOrder, Wallet } from '@ledova/shared-types';
import { CustomModal } from '../../../components/modal';
import { QRDisplay, QRScanner } from '../../../components/qr';
import { decodeKeystoneMessageSignature } from '../../../utils/keystone/urDecoder';
import { useOrderSigning } from '../useOrderSigning';
import { SoftwareSignMessage } from './SoftwareSignMessage';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface OrderSigningModalProps {
  visible: boolean;
  onClose: () => void;
  mode: 'create' | 'cancel';
  orderData?: CreateOrderRequest;
  orderUuid?: string;
  orderSymbol?: string;
  wallet: Wallet | null;
  onSuccess?: (order: TransferOrder) => void;
}

export function OrderSigningModal({
  visible,
  onClose,
  mode,
  orderData,
  orderUuid,
  orderSymbol,
  wallet,
  onSuccess,
}: OrderSigningModalProps) {
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
    summaryValueMono: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      fontFamily: 'monospace',
    },
    errorBox: {
      padding: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.error.default + '1A',
      borderWidth: 1,
      borderColor: theme.colors.error.default + '33',
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.icon,
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
  const signing = useOrderSigning({ mode, orderData, orderUuid, wallet, onSuccess });

  useEffect(() => {
    if (visible) {
      signing.start();
    } else {
      signing.reset();
    }
  }, [visible]);

  useEffect(() => {
    if (signing.step === 'success') {
      const timer = setTimeout(() => onClose(), 2000);
      return () => clearTimeout(timer);
    }
  }, [signing.step, onClose]);

  const handleClose = () => {
    if (signing.isSubmitting) return;
    onClose();
  };

  const isCreating = mode === 'create';

  const getConfirmLabel = (): string | undefined => {
    switch (signing.step) {
      case 'instructions':
        return signing.isSoftwareWallet ? 'Sign with Biometric' : 'Show QR Code';
      case 'show-qr':
        return "I've Signed It";
      default:
        return undefined;
    }
  };

  const getCancelLabel = (): string => {
    if (['show-qr', 'scan-signature', 'error'].includes(signing.step)) return 'Back';
    return 'Cancel';
  };

  const handleConfirm = () => {
    switch (signing.step) {
      case 'instructions':
        signing.proceedToSign();
        break;
      case 'show-qr':
        signing.proceedToScanSignature();
        break;
    }
  };

  const handleCancel = () => {
    if (['show-qr', 'scan-signature', 'error'].includes(signing.step)) {
      signing.goBack();
    } else {
      handleClose();
    }
  };

  const renderContent = () => {
    switch (signing.step) {
      case 'getting-message':
        return (
          <View style={styles.centeredContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.loadingText}>Preparing signing data...</Text>
          </View>
        );

      case 'instructions':
        return (
          <View style={styles.contentContainer}>
            <Text style={styles.description}>
              {isCreating
                ? `Sign this order with your ${signing.isSoftwareWallet ? 'software' : 'hardware'} wallet to authorize the trade.`
                : `Sign this cancellation with your ${signing.isSoftwareWallet ? 'software' : 'hardware'} wallet to cancel your order.`}
            </Text>

            {signing.messageData && (
              <View style={styles.summaryBox}>
                {isCreating && 'tokenUuid' in signing.messageData && (
                  <>
                    <View style={styles.summaryRow}>
                      <Text style={styles.summaryLabel}>Type</Text>
                      <Text style={styles.summaryValue}>{signing.messageData.orderType.toUpperCase()}</Text>
                    </View>
                    <View style={styles.summaryRow}>
                      <Text style={styles.summaryLabel}>Quantity</Text>
                      <Text style={styles.summaryValue}>{signing.messageData.quantity} shares</Text>
                    </View>
                    <View style={styles.summaryRow}>
                      <Text style={styles.summaryLabel}>Price</Text>
                      <Text style={styles.summaryValue}>${signing.messageData.pricePerShare}</Text>
                    </View>
                  </>
                )}
                {!isCreating && 'orderUuid' in signing.messageData && (
                  <>
                    <View style={styles.summaryRow}>
                      <Text style={styles.summaryLabel}>Order</Text>
                      <Text style={styles.summaryValueMono}>{signing.messageData.orderUuid.slice(0, 8)}...</Text>
                    </View>
                    {orderSymbol && (
                      <View style={styles.summaryRow}>
                        <Text style={styles.summaryLabel}>Token</Text>
                        <Text style={styles.summaryValue}>{orderSymbol}</Text>
                      </View>
                    )}
                  </>
                )}
              </View>
            )}

            {signing.error && (
              <View style={styles.errorBox}>
                <Text style={styles.errorText}>{signing.error}</Text>
              </View>
            )}
          </View>
        );

      case 'show-qr':
        return (
          <View style={styles.contentContainer}>
            <Text style={styles.description}>
              Scan this QR code with your hardware wallet to sign the {isCreating ? 'order' : 'cancellation'}.
            </Text>
            {signing.qrData && <QRDisplay data={signing.qrData.cborHex} isUR />}
          </View>
        );

      case 'signing-software':
        return (
          <SoftwareSignMessage
            statusTitle="Signing Message..."
            statusDescription={`Authenticating and signing this ${isCreating ? 'order' : 'cancellation'}...`}
          />
        );

      case 'submitting':
        return (
          <View style={styles.centeredContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.loadingText}>{isCreating ? 'Creating order...' : 'Cancelling order...'}</Text>
          </View>
        );

      case 'success':
        return (
          <View style={styles.centeredContainer}>
            <CheckCircleIcon size={theme.icon.sizes.hero} color={theme.colors.status.success.icon} weight="fill" />
            <Text style={styles.successTitle}>{isCreating ? 'Order Created!' : 'Order Cancelled!'}</Text>
            <Text style={styles.successDesc}>
              {isCreating ? 'Your order has been placed successfully.' : 'Your order has been cancelled successfully.'}
            </Text>
          </View>
        );

      case 'error':
        return (
          <View style={styles.centeredContainer}>
            <WarningCircleIcon size={theme.icon.sizes.hero} color={theme.colors.status.error.icon} weight="fill" />
            <Text style={styles.errorTitle}>{isCreating ? 'Order Failed' : 'Cancellation Failed'}</Text>
            <Text style={styles.errorDesc}>{signing.error || 'An error occurred'}</Text>
          </View>
        );

      default:
        return null;
    }
  };

  const showConfirm = ['instructions', 'show-qr'].includes(signing.step);
  const showCancel = !['getting-message', 'submitting', 'success'].includes(signing.step);

  return (
    <>
      <CustomModal
        visible={visible && signing.step !== 'scan-signature'}
        onClose={handleClose}
        showFooter={showConfirm || showCancel}
        showCancelButton={showCancel}
        cancelLabel={getCancelLabel()}
        onCancel={handleCancel}
        confirmLabel={getConfirmLabel()}
        onConfirm={showConfirm ? handleConfirm : undefined}
        confirmDisabled={signing.step === 'instructions' && (!signing.messageData || !wallet)}
      >
        {renderContent()}
      </CustomModal>

      <QRScanner
        visible={visible && signing.step === 'scan-signature'}
        onClose={() => signing.goBack()}
        onScan={(data) => {
          const decoded = decodeKeystoneMessageSignature(data);
          if (decoded) {
            signing.handleSignatureReceived(decoded);
          }
        }}
        title="Scan Signature"
        subtitle="Point your camera at the signature QR code on your hardware wallet."
      />
    </>
  );
}
