import { useEffect, useCallback, useState } from 'react';
import {
  ShieldCheckIcon,
  QrCodeIcon,
  CameraIcon,
  CheckCircleIcon,
  ArrowLeftIcon,
  KeyIcon,
} from '@phosphor-icons/react';
import { QRCodeSVG } from 'qrcode.react';
import { DESIGN_TOKENS, getWalletVerificationEvmChainId } from '@ledova/shared';
import type { Wallet } from '@ledova/shared';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_XXL = DESIGN_TOKENS.icon.sizes.xxl;
const ICON_DISPLAY = DESIGN_TOKENS.icon.sizes.display;
import { Modal } from '@components/Modal';
import { SeedPhraseInput } from '@components/SeedPhraseInput';
import { useQRScanner, QRScannerView } from '@components/qr';
import { useWalletVerification } from '../hooks/useWalletVerification';
import { decodeKeystoneMessageSignature } from '@utils/keystone/urDecoder';

interface WalletVerificationModalProps {
  isOpen: boolean;
  wallet: Wallet | null;
  onClose: () => void;
}

export function WalletVerificationModal({ isOpen, wallet, onClose }: WalletVerificationModalProps) {
  const {
    verificationStep,
    challengeQrData,
    verificationError,
    verificationSuccess,
    isRequestingChallenge,
    isVerifying,
    isSigningWithSeedPhrase,
    startVerification,
    proceedToScanSignature,
    handleSignatureScanned,
    signWithSeedPhrase,
    goBack,
    reset,
  } = useWalletVerification();

  const [seedPhrase, setSeedPhrase] = useState('');

  const { error: scannerError, stopScanner } = useQRScanner({
    scannerId: 'qr-scanner',
    onScanSuccess: (text) => {
      const signature = decodeKeystoneMessageSignature(text);
      if (signature) {
        handleSignatureScanned(signature);
      }
    },
    enabled: verificationStep === 'scan-signature',
  });

  const handleClose = useCallback(() => {
    stopScanner();
    setSeedPhrase('');
    reset();
    onClose();
  }, [onClose, reset, stopScanner]);

  useEffect(() => {
    if (verificationSuccess) {
      const timer = setTimeout(() => {
        handleClose();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [verificationSuccess, handleClose]);

  const handleStartVerification = () => {
    if (wallet) {
      startVerification(wallet, 'hardware');
    }
  };

  const handleStartSeedPhraseVerification = () => {
    if (wallet) {
      setSeedPhrase('');
      startVerification(wallet, 'software');
    }
  };

  const handleBackFromSeedPhrase = () => {
    setSeedPhrase('');
    goBack();
  };

  const handleSignWithSeedPhrase = () => {
    const phrase = seedPhrase;
    setSeedPhrase('');
    void signWithSeedPhrase(phrase);
  };

  if (!wallet) return null;

  const supportsSeedPhraseSigning = getWalletVerificationEvmChainId(wallet.chain) !== null;

  const renderStepContent = () => {
    switch (verificationStep) {
      case 'instructions':
        return (
          <div className="space-y-6">
            <div className="flex justify-center">
              <div className="p-4 bg-brand-mid/10 rounded-full">
                <ShieldCheckIcon size={ICON_XXL} className="text-brand-mid" />
              </div>
            </div>

            <div className="text-center">
              <h3 className="text-lg font-semibold text-text-primary mb-2">Verify Your Wallet</h3>
              <p className="text-sm text-text-muted">
                Prove ownership of this wallet by signing a verification message with your hardware wallet.
              </p>
            </div>

            <div className="space-y-3">
              <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                  1
                </span>
                <p className="text-sm text-text-secondary">Scan the challenge QR code with your hardware wallet</p>
              </div>
              <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                  2
                </span>
                <p className="text-sm text-text-secondary">Sign the message on your hardware wallet</p>
              </div>
              <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                  3
                </span>
                <p className="text-sm text-text-secondary">Scan the signature QR code from your hardware wallet</p>
              </div>
            </div>

            {verificationError && (
              <div className="p-3 bg-error-light/10 border border-error-light/20 rounded-lg">
                <p className="text-sm text-error-light">{verificationError}</p>
              </div>
            )}

            <button
              type="button"
              onClick={handleStartVerification}
              disabled={isRequestingChallenge}
              className="w-full py-3 bg-brand-mid text-white text-sm font-medium rounded-lg hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isRequestingChallenge ? 'Generating Challenge...' : 'Continue'}
            </button>

            {supportsSeedPhraseSigning && (
              <button
                type="button"
                onClick={handleStartSeedPhraseVerification}
                disabled={isRequestingChallenge}
                className="w-full py-3 bg-surface-tertiary text-text-primary text-sm font-medium rounded-lg hover:bg-surface-disabled disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                No hardware wallet? Sign with a seed phrase
              </button>
            )}
          </div>
        );

      case 'show-challenge-qr':
        return (
          <div className="space-y-6">
            <button
              type="button"
              onClick={goBack}
              className="flex items-center gap-1 text-sm text-text-muted hover:text-text-primary transition-colors"
            >
              <ArrowLeftIcon size={ICON_SM} />
              Back
            </button>

            <div className="flex justify-center">
              <div className="p-4 bg-brand-mid/10 rounded-full">
                <QrCodeIcon size={ICON_XXL} className="text-brand-mid" />
              </div>
            </div>

            <div className="text-center">
              <h3 className="text-lg font-semibold text-text-primary mb-2">Scan Challenge</h3>
              <p className="text-sm text-text-muted">Scan this QR code with your hardware wallet</p>
            </div>

            {challengeQrData && (
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <QRCodeSVG value={challengeQrData} size={220} level="M" />
              </div>
            )}

            {verificationError && (
              <div className="p-3 bg-error-light/10 border border-error-light/20 rounded-lg">
                <p className="text-sm text-error-light">{verificationError}</p>
              </div>
            )}

            <button
              type="button"
              onClick={proceedToScanSignature}
              className="w-full py-3 bg-brand-mid text-white text-sm font-medium rounded-lg hover:bg-brand transition-colors"
            >
              I&apos;ve Signed the Message
            </button>
          </div>
        );

      case 'scan-signature':
        return (
          <div className="space-y-6">
            <button
              type="button"
              onClick={goBack}
              className="flex items-center gap-1 text-sm text-text-muted hover:text-text-primary transition-colors"
            >
              <ArrowLeftIcon size={ICON_SM} />
              Back
            </button>

            <div className="flex justify-center">
              <div className="p-4 bg-brand-mid/10 rounded-full">
                <CameraIcon size={ICON_XXL} className="text-brand-mid" />
              </div>
            </div>

            <div className="text-center">
              <h3 className="text-lg font-semibold text-text-primary mb-2">Scan Signature</h3>
              <p className="text-sm text-text-muted">
                Point your camera at the signature QR code on your hardware wallet
              </p>
            </div>

            <QRScannerView scannerId="qr-scanner" error={scannerError} />

            {verificationError && (
              <div className="p-3 bg-error-light/10 border border-error-light/20 rounded-lg">
                <p className="text-sm text-error-light">{verificationError}</p>
              </div>
            )}

            {isVerifying && (
              <div className="flex items-center justify-center gap-2 py-3">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-brand-mid"></div>
                <span className="text-sm text-text-muted">Verifying signature...</span>
              </div>
            )}
          </div>
        );

      case 'sign-software':
        return (
          <div className="space-y-6">
            <button
              type="button"
              onClick={handleBackFromSeedPhrase}
              className="flex items-center gap-1 text-sm text-text-muted hover:text-text-primary transition-colors"
            >
              <ArrowLeftIcon size={ICON_SM} />
              Back
            </button>

            <div className="flex justify-center">
              <div className="p-4 bg-brand-mid/10 rounded-full">
                <KeyIcon size={ICON_XXL} className="text-brand-mid" />
              </div>
            </div>

            <div className="text-center">
              <h3 className="text-lg font-semibold text-text-primary mb-2">Sign with Seed Phrase</h3>
              <p className="text-sm text-text-muted">
                Enter the seed phrase for wallet{' '}
                <span className="font-mono text-xs text-text-secondary">
                  {wallet.address.slice(0, 6)}...{wallet.address.slice(-4)}
                </span>
              </p>
            </div>

            <SeedPhraseInput
              value={seedPhrase}
              onChange={setSeedPhrase}
              disabled={isSigningWithSeedPhrase || isVerifying}
            />

            {verificationError && (
              <div className="p-3 bg-error-light/10 border border-error-light/20 rounded-lg">
                <p className="text-sm text-error-light">{verificationError}</p>
                {!seedPhrase && (
                  <p className="text-xs text-error-light/80 mt-1">
                    The phrase was cleared when it was handed to the signer. Enter it again to retry.
                  </p>
                )}
              </div>
            )}

            <button
              type="button"
              onClick={handleSignWithSeedPhrase}
              disabled={!seedPhrase.trim() || isSigningWithSeedPhrase || isVerifying}
              className="w-full py-3 bg-brand-mid text-white text-sm font-medium rounded-lg hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isSigningWithSeedPhrase || isVerifying ? 'Verifying...' : 'Sign and Verify'}
            </button>
          </div>
        );

      case 'success':
        return (
          <div className="space-y-6 py-8">
            <div className="flex justify-center">
              <div className="p-4 bg-success-light/10 rounded-full">
                <CheckCircleIcon size={ICON_DISPLAY} className="text-success-light" />
              </div>
            </div>

            <div className="text-center">
              <h3 className="text-xl font-semibold text-success-light mb-2">Wallet Verified!</h3>
              <p className="text-sm text-text-muted">Your wallet has been successfully verified.</p>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Verify Wallet" showFooter={false}>
      {renderStepContent()}
    </Modal>
  );
}
