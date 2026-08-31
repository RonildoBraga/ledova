/**
 * SwapSigningFlow Component
 * Modal flow for signing an atomic swap order with hardware wallet.
 * Follows the same pattern as WalletVerificationModal for consistent UX.
 */

import { useEffect, useCallback } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { XIcon, ArrowsDownUpIcon, CheckCircleIcon, WarningCircleIcon, SpinnerGapIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared-constants';
import { AnimatedQRCode } from '@keystonehq/animated-qr';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;
const ICON_HERO = DESIGN_TOKENS.icon.sizes.hero;
const ICON_DISPLAY = DESIGN_TOKENS.icon.sizes.display;
import { useQRScanner, QRScannerView } from '@components/qr';
import type { SwapOrder, Wallet } from '@ledova/shared-types';
import { useAtomicSwapSigning } from '../hooks/useAtomicSwapSigning';
import { decodeKeystoneMessageSignature, decodeKeystoneSignedTransaction } from '@utils/keystone/urDecoder';

interface SwapSigningFlowProps {
  isOpen: boolean;
  onClose: () => void;
  swap: SwapOrder | null;
  walletAddress: string;
  wallet: Wallet | null;
  orderUuid?: string;
}

export function SwapSigningFlow({ isOpen, onClose, swap, walletAddress, wallet, orderUuid }: SwapSigningFlowProps) {
  const {
    signingStep,
    swapData,
    swapQrCborHex,
    swapQrType,
    signingError,
    signingSuccess,
    // Approval state
    needsApproval,
    approvalTokenSymbol,
    approvalQrCborHex,
    approvalQrType,
    unsignedApprovalTx,
    // Loading states
    isLoadingSwapData,
    isLoadingApprovalData,
    isReady,
    isSubmitting,
    isBroadcastingApproval,
    // Software wallet
    isSoftwareWallet,
    seedPhrase,
    setSeedPhrase,
    // Actions
    startSigning,
    proceedToScanApprovalSignature,
    handleApprovalSignatureScanned,
    handleSoftwareApprovalSign,
    handleSoftwareSwapSign,
    proceedToScanSignature,
    handleSignatureScanned,
    goBack,
    reset,
  } = useAtomicSwapSigning({
    orderUuid: orderUuid || swap?.sellOrderUuid,
    walletAddress,
    wallet,
  });

  const { error: approvalScannerError, stopScanner: stopApprovalScanner } = useQRScanner({
    scannerId: 'approval-qr-scanner',
    onScanSuccess: (text) => {
      const decoded = decodeKeystoneSignedTransaction(text, unsignedApprovalTx || undefined);
      if (decoded) {
        handleApprovalSignatureScanned(decoded);
      }
    },
    enabled: signingStep === 'scan-approval-signature',
  });

  const { error: swapScannerError, stopScanner: stopSwapScanner } = useQRScanner({
    scannerId: 'swap-qr-scanner',
    onScanSuccess: (text) => {
      const decoded = decodeKeystoneMessageSignature(text);
      if (decoded) {
        handleSignatureScanned(decoded);
      }
    },
    enabled: signingStep === 'scan-signature',
  });

  // Handle modal close
  const handleClose = useCallback(() => {
    if (isSubmitting || isBroadcastingApproval) return;
    stopApprovalScanner();
    stopSwapScanner();
    reset();
    onClose();
  }, [onClose, reset, isSubmitting, isBroadcastingApproval, stopApprovalScanner, stopSwapScanner]);

  // Auto-close on success
  useEffect(() => {
    if (signingSuccess) {
      const timer = setTimeout(() => {
        handleClose();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [signingSuccess, handleClose]);

  // Reset when modal opens
  useEffect(() => {
    if (isOpen) {
      reset();
    }
  }, [isOpen, reset]);

  const renderStepContent = () => {
    // Loading state
    if (isLoadingSwapData || (swapData && isLoadingApprovalData)) {
      return (
        <div className="flex flex-col items-center justify-center py-8 gap-3">
          <SpinnerGapIcon size={ICON_XL} className="text-brand-mid animate-spin" />
          <p className="text-sm text-text-muted">
            {isLoadingSwapData ? 'Loading swap data...' : 'Checking approval requirements...'}
          </p>
        </div>
      );
    }

    switch (signingStep) {
      case 'instructions':
        return (
          <div className="space-y-5">
            {/* Description */}
            <p className="text-sm text-text-muted">
              Sign this swap transaction with your {isSoftwareWallet ? 'seed phrase' : 'hardware wallet'} to authorize
              the trade.
            </p>

            {/* Swap Summary */}
            {swapData && (
              <div className="bg-surface-tertiary rounded-lg p-4 space-y-2">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="text-text-muted">You are the</div>
                  <div
                    className={`font-medium ${swapData.userRole === 'seller' ? 'text-error-light' : 'text-success-light'}`}
                  >
                    {swapData.userRole === 'seller' ? 'Seller' : 'Buyer'}
                  </div>
                  <div className="text-text-muted">Shares</div>
                  <div className="text-text-primary">
                    {swapData.swapOrder.shareAmount.toLocaleString()} {swapData.swapOrder.shareTokenSymbol}
                  </div>
                  <div className="text-text-muted">Payment</div>
                  <div className="text-text-primary">
                    ${(swapData.swapOrder.paymentAmount / 100).toFixed(2)} {swapData.swapOrder.paymentTokenSymbol}
                  </div>
                </div>
              </div>
            )}

            {/* Approval Notice */}
            {needsApproval && approvalTokenSymbol && (
              <div className="p-3 bg-warning/10 border border-warning/20 rounded-lg">
                <p className="text-sm text-warning">
                  <strong>Approval Required:</strong> You need to approve the swap contract to transfer your{' '}
                  {approvalTokenSymbol} tokens before signing the swap.
                </p>
              </div>
            )}

            {/* Instructions */}
            <div className="space-y-3">
              {needsApproval && (
                <>
                  <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                    <span className="flex-shrink-0 w-6 h-6 bg-warning text-white text-sm font-semibold rounded-full flex items-center justify-center">
                      1
                    </span>
                    <p className="text-sm text-text-secondary">First, approve the swap contract (one-time per token)</p>
                  </div>
                  <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                    <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                      2
                    </span>
                    <p className="text-sm text-text-secondary">Then sign the swap authorization</p>
                  </div>
                </>
              )}
              {!needsApproval &&
                (isSoftwareWallet ? (
                  <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                    <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                      1
                    </span>
                    <p className="text-sm text-text-secondary">
                      Enter your seed phrase to sign the swap. It is used locally and never stored.
                    </p>
                  </div>
                ) : (
                  <>
                    <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                      <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                        1
                      </span>
                      <p className="text-sm text-text-secondary">Scan the swap QR code with your hardware wallet</p>
                    </div>
                    <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                      <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                        2
                      </span>
                      <p className="text-sm text-text-secondary">
                        Review and sign the transaction on your hardware wallet
                      </p>
                    </div>
                    <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                      <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                        3
                      </span>
                      <p className="text-sm text-text-secondary">
                        Scan the signature QR code from your hardware wallet
                      </p>
                    </div>
                  </>
                ))}
            </div>

            {signingError && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{signingError}</p>
              </div>
            )}

            {/* Footer Buttons */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={handleClose}
                className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={startSigning}
                disabled={!isReady}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isLoadingApprovalData ? 'Loading...' : needsApproval ? 'Start Approval' : 'Continue'}
              </button>
            </div>
          </div>
        );

      case 'show-approval-qr':
        return (
          <div className="space-y-5">
            {/* Description */}
            <p className="text-sm text-text-muted">
              Scan this QR code to approve the swap contract to transfer your {approvalTokenSymbol} tokens.
            </p>

            {approvalQrCborHex && approvalQrType && (
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <AnimatedQRCode cbor={approvalQrCborHex} type={approvalQrType} />
              </div>
            )}

            {signingError && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{signingError}</p>
              </div>
            )}

            {/* Footer Buttons */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={goBack}
                className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                onClick={proceedToScanApprovalSignature}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-warning hover:bg-warning transition-colors"
              >
                I&apos;ve Signed It
              </button>
            </div>
          </div>
        );

      case 'scan-approval-signature':
        return (
          <div className="space-y-5">
            {/* Description */}
            <p className="text-sm text-text-muted">
              Point your camera at the signed approval QR code on your hardware wallet.
            </p>

            <QRScannerView scannerId="approval-qr-scanner" error={approvalScannerError} />

            {signingError && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{signingError}</p>
              </div>
            )}

            {/* Footer Button */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={goBack}
                className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
              >
                Back
              </button>
            </div>
          </div>
        );

      case 'broadcasting-approval':
        return (
          <div className="flex flex-col items-center justify-center py-8 gap-3">
            <SpinnerGapIcon size={ICON_XL} className="text-warning animate-spin" />
            <p className="text-sm text-text-muted">Broadcasting approval transaction...</p>
            <p className="text-xs text-text-subtle">This may take a moment</p>
          </div>
        );

      case 'show-swap-qr':
        return (
          <div className="space-y-5">
            {/* Description */}
            <p className="text-sm text-text-muted">Scan this QR code with your hardware wallet to sign the swap.</p>

            {swapQrCborHex && swapQrType && (
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <AnimatedQRCode cbor={swapQrCborHex} type={swapQrType} />
              </div>
            )}

            {signingError && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{signingError}</p>
              </div>
            )}

            {/* Footer Buttons */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={goBack}
                className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                onClick={proceedToScanSignature}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand transition-colors"
              >
                I&apos;ve Signed It
              </button>
            </div>
          </div>
        );

      case 'scan-signature':
        return (
          <div className="space-y-5">
            {/* Description */}
            <p className="text-sm text-text-muted">
              Point your camera at the signature QR code on your hardware wallet.
            </p>

            <QRScannerView scannerId="swap-qr-scanner" error={swapScannerError} />

            {signingError && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{signingError}</p>
              </div>
            )}

            {/* Footer Button */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={goBack}
                className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
              >
                Back
              </button>
            </div>
          </div>
        );

      case 'signing-approval-software':
      case 'signing-swap-software': {
        const isApproval = signingStep === 'signing-approval-software';
        return (
          <div className="space-y-5">
            <p className="text-sm text-text-muted">
              Enter the seed phrase for wallet{' '}
              <span className="font-mono text-xs text-text-secondary">
                {walletAddress.slice(0, 6)}...{walletAddress.slice(-4)}
              </span>
              {isApproval ? ' to approve token transfer' : ' to sign the swap'}
            </p>

            <div>
              <label className="block text-sm font-medium text-text-secondary mb-2">Seed Phrase</label>
              <textarea
                value={seedPhrase}
                onChange={(e) => setSeedPhrase(e.target.value)}
                placeholder="Enter your 12 or 24 word seed phrase"
                rows={3}
                className="w-full px-3 py-2 rounded-lg bg-surface-tertiary border border-border-subtle text-text-primary placeholder-text-muted text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-mid/50"
                style={{ WebkitTextSecurity: 'disc' } as React.CSSProperties}
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
              />
              <p className="text-xs text-text-muted mt-1">
                Your seed phrase is used locally for signing and is never stored or transmitted.
              </p>
            </div>

            {signingError && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{signingError}</p>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={goBack}
                className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                onClick={isApproval ? handleSoftwareApprovalSign : handleSoftwareSwapSign}
                disabled={!seedPhrase.trim()}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Sign
              </button>
            </div>
          </div>
        );
      }

      case 'submitting':
        return (
          <div className="flex flex-col items-center justify-center py-8 gap-3">
            <SpinnerGapIcon size={ICON_XL} className="text-brand-mid animate-spin" />
            <p className="text-sm text-text-muted">Submitting signature...</p>
            <p className="text-xs text-text-subtle">This may take a moment</p>
          </div>
        );

      case 'success':
        return (
          <div className="space-y-6 py-8">
            <div className="flex justify-center">
              <div className="p-4 bg-success/10 rounded-full">
                <CheckCircleIcon size={ICON_DISPLAY} className="text-success" weight="fill" />
              </div>
            </div>

            <div className="text-center">
              <h3 className="text-xl font-semibold text-success mb-2">Signature Submitted!</h3>
              <p className="text-sm text-text-muted">
                Your signature has been recorded. The swap will execute once both parties have signed.
              </p>
            </div>
          </div>
        );

      case 'error':
        return (
          <div className="flex flex-col items-center justify-center py-8 gap-4">
            <div className="w-16 h-16 rounded-full bg-error-light/10 flex items-center justify-center">
              <WarningCircleIcon size={ICON_HERO} className="text-error-light" weight="fill" />
            </div>
            <div className="text-center">
              <h3 className="text-lg font-semibold text-text-primary">Signing Failed</h3>
              <p className="text-sm text-text-muted mt-1">{signingError || 'An error occurred'}</p>
            </div>
            <div className="flex gap-3 w-full">
              <button
                onClick={handleClose}
                className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
              >
                Close
              </button>
              <button
                onClick={goBack}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand transition-colors"
              >
                Try Again
              </button>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <Transition show={isOpen}>
      <Dialog onClose={handleClose} className="relative z-50">
        {/* Backdrop */}
        <Transition.Child
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" />
        </Transition.Child>

        {/* Modal */}
        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-md bg-surface-raised rounded-xl border border-border shadow-xl overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
                  <Dialog.Title className="text-lg font-semibold text-text-primary flex items-center gap-2">
                    <ArrowsDownUpIcon size={ICON_MD} className="text-brand-light" />
                    Sign Atomic Swap
                  </Dialog.Title>
                  <button
                    onClick={handleClose}
                    disabled={isSubmitting || isBroadcastingApproval}
                    className="p-1 rounded-lg hover:bg-surface-tertiary transition-colors disabled:opacity-50"
                  >
                    <XIcon size={ICON_MD} className="text-text-muted" />
                  </button>
                </div>

                {/* Content */}
                <div className="p-4">{renderStepContent()}</div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
