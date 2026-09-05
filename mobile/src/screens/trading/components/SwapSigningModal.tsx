import React, { useEffect } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { CheckCircleIcon, WarningCircleIcon, ShieldCheckIcon } from 'phosphor-react-native';
import type { SwapOrder, Wallet } from '@ledova/shared';
import { CustomModal } from '../../../components/modal';
import { QRDisplay, QRScanner } from '../../../components/qr';
import { decodeKeystoneMessageSignature } from '../../../utils/keystone/urDecoder';
import { useAtomicSwapSigning } from '../useAtomicSwapSigning';
import { SoftwareSignMessage } from './SoftwareSignMessage';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface SwapSigningModalProps {
  visible: boolean;
  onClose: () => void;
  swap: SwapOrder | null;
  wallet: Wallet | null;
  onSuccess?: () => void;
}

export function SwapSigningModal({ visible, onClose, swap, wallet, onSuccess }: SwapSigningModalProps) {
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
    loadingSubtext: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
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
    approvalNotice: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: theme.spacing.sm,
      padding: theme.spacing.md,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.warning.default + '1A',
      borderWidth: 1,
      borderColor: theme.colors.warning.default + '33',
    },
    approvalNoticeText: {
      flex: 1,
    },
    approvalTitle: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.status.warning.icon,
    },
    approvalDesc: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      marginTop: 4,
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
  const isSeller = swap ? wallet?.address.toLowerCase() === swap.sellerAddress.toLowerCase() : false;
  const walletAddress = swap ? (isSeller ? swap.sellerAddress : swap.buyerAddress) : '';
  const orderUuid = swap ? (isSeller ? swap.sellOrderUuid : swap.buyOrderUuid) : undefined;

  const signing = useAtomicSwapSigning({
    orderUuid,
    walletAddress,
    wallet,
  });

  useEffect(() => {
    if (!visible) {
      signing.reset();
    }
  }, [visible]);

  useEffect(() => {
    if (signing.signingStep === 'success') {
      onSuccess?.();
      const timer = setTimeout(() => onClose(), 2000);
      return () => clearTimeout(timer);
    }
  }, [signing.signingStep, onClose, onSuccess]);

  const handleClose = () => {
    if (signing.isSubmitting || signing.isBroadcastingApproval) return;
    onClose();
  };

  const getConfirmLabel = (): string | undefined => {
    switch (signing.signingStep) {
      case 'instructions':
        if (!signing.isReady) return undefined;
        if (signing.needsApproval) {
          return signing.isSoftwareWallet ? 'Approve with Biometric' : 'Show Approval QR';
        }
        return signing.isSoftwareWallet ? 'Sign with Biometric' : 'Show QR Code';
      case 'show-approval-qr':
        return "I've Signed Approval";
      case 'show-swap-qr':
        return "I've Signed It";
      default:
        return undefined;
    }
  };

  const getCancelLabel = (): string => {
    if (
      ['show-approval-qr', 'scan-approval-signature', 'show-swap-qr', 'scan-signature', 'error'].includes(
        signing.signingStep,
      )
    ) {
      return 'Back';
    }
    return 'Cancel';
  };

  const handleConfirm = () => {
    switch (signing.signingStep) {
      case 'instructions':
        signing.startSigning();
        break;
      case 'show-approval-qr':
        signing.proceedToScanApprovalSignature();
        break;
      case 'show-swap-qr':
        signing.proceedToScanSignature();
        break;
    }
  };

  const handleCancel = () => {
    if (
      ['show-approval-qr', 'scan-approval-signature', 'show-swap-qr', 'scan-signature', 'error'].includes(
        signing.signingStep,
      )
    ) {
      signing.goBack();
    } else {
      handleClose();
    }
  };

  const isQrScanStep = signing.signingStep === 'scan-approval-signature' || signing.signingStep === 'scan-signature';

  const renderContent = () => {
    if (!swap) return null;

    switch (signing.signingStep) {
      case 'instructions': {
        if (!signing.isReady) {
          return (
            <View style={styles.centeredContainer}>
              <ActivityIndicator size="large" color={theme.colors.interactive.default} />
              <Text style={styles.loadingText}>Loading swap data...</Text>
            </View>
          );
        }

        const paymentDisplay = (swap.paymentAmount / 100).toFixed(2);

        return (
          <View style={styles.contentContainer}>
            <Text style={styles.description}>
              Sign this swap to complete the trade.{' '}
              {signing.needsApproval ? 'An approval transaction is required first.' : ''}
            </Text>

            <View style={styles.summaryBox}>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Token</Text>
                <Text style={styles.summaryValue}>{swap.shareTokenSymbol}</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Shares</Text>
                <Text style={styles.summaryValue}>{swap.shareAmount.toLocaleString()}</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Payment</Text>
                <Text style={styles.summaryValue}>${paymentDisplay}</Text>
              </View>
              <View style={styles.summaryRow}>
                <Text style={styles.summaryLabel}>Your Role</Text>
                <Text style={styles.summaryValue}>
                  {walletAddress.toLowerCase() === swap.sellerAddress.toLowerCase() ? 'Seller' : 'Buyer'}
                </Text>
              </View>
            </View>

            {signing.needsApproval && (
              <View style={styles.approvalNotice}>
                <ShieldCheckIcon size={theme.icon.sizes.md} color={theme.colors.status.warning.icon} />
                <View style={styles.approvalNoticeText}>
                  <Text style={styles.approvalTitle}>Token Approval Required</Text>
                  <Text style={styles.approvalDesc}>
                    You need to approve the transfer of {signing.approvalTokenSymbol || 'tokens'} before signing the
                    swap.
                  </Text>
                </View>
              </View>
            )}
          </View>
        );
      }

      case 'show-approval-qr':
        return (
          <View style={styles.contentContainer}>
            <Text style={styles.description}>
              Scan this QR code with your hardware wallet to sign the token approval transaction.
            </Text>
            {signing.approvalQrCborHex && <QRDisplay data={signing.approvalQrCborHex} isUR />}
          </View>
        );

      case 'signing-approval-software':
        return (
          <SoftwareSignMessage
            statusTitle="Signing Approval..."
            statusDescription="Authenticating and signing the token approval..."
          />
        );

      case 'broadcasting-approval':
        return (
          <View style={styles.centeredContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.loadingText}>Broadcasting approval...</Text>
            <Text style={styles.loadingSubtext}>This may take a moment.</Text>
          </View>
        );

      case 'show-swap-qr':
        return (
          <View style={styles.contentContainer}>
            <Text style={styles.description}>Scan this QR code with your hardware wallet to sign the atomic swap.</Text>
            {signing.swapQrCborHex && <QRDisplay data={signing.swapQrCborHex} isUR />}
          </View>
        );

      case 'signing-swap-software':
        return (
          <SoftwareSignMessage
            statusTitle="Signing Swap..."
            statusDescription="Authenticating and signing the atomic swap..."
          />
        );

      case 'submitting':
        return (
          <View style={styles.centeredContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.loadingText}>Submitting signature...</Text>
          </View>
        );

      case 'success':
        return (
          <View style={styles.centeredContainer}>
            <CheckCircleIcon size={theme.icon.sizes.hero} color={theme.colors.status.success.icon} weight="fill" />
            <Text style={styles.successTitle}>Swap Signed!</Text>
            <Text style={styles.successDesc}>Your signature has been submitted successfully.</Text>
          </View>
        );

      case 'error':
        return (
          <View style={styles.centeredContainer}>
            <WarningCircleIcon size={theme.icon.sizes.hero} color={theme.colors.status.error.icon} weight="fill" />
            <Text style={styles.errorTitle}>Signing Failed</Text>
            <Text style={styles.errorDesc}>{signing.signingError || 'An error occurred'}</Text>
          </View>
        );

      default:
        return null;
    }
  };

  const showConfirm = ['instructions', 'show-approval-qr', 'show-swap-qr'].includes(signing.signingStep);
  const showCancel = ![
    'checking-approval',
    'broadcasting-approval',
    'submitting',
    'success',
    'signing-approval-software',
    'signing-swap-software',
  ].includes(signing.signingStep);

  return (
    <>
      <CustomModal
        visible={visible && !isQrScanStep}
        onClose={handleClose}
        showFooter={showConfirm || showCancel}
        showCancelButton={showCancel}
        cancelLabel={getCancelLabel()}
        onCancel={handleCancel}
        confirmLabel={getConfirmLabel()}
        onConfirm={showConfirm ? handleConfirm : undefined}
        confirmDisabled={signing.signingStep === 'instructions' && !signing.isReady}
      >
        {renderContent()}
      </CustomModal>

      <QRScanner
        visible={visible && signing.signingStep === 'scan-approval-signature'}
        onClose={() => signing.goBack()}
        onScan={(data) => {
          const decoded = decodeKeystoneMessageSignature(data);
          if (decoded) {
            signing.handleApprovalSignatureScanned(decoded);
          }
        }}
        title="Scan Approval Signature"
        subtitle="Point your camera at the approval signature QR code on your hardware wallet."
      />

      <QRScanner
        visible={visible && signing.signingStep === 'scan-signature'}
        onClose={() => signing.goBack()}
        onScan={(data) => {
          const decoded = decodeKeystoneMessageSignature(data);
          if (decoded) {
            signing.handleSignatureScanned(decoded);
          }
        }}
        title="Scan Swap Signature"
        subtitle="Point your camera at the signature QR code on your hardware wallet."
      />
    </>
  );
}
