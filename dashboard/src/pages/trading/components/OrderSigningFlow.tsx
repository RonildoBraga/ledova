import { useEffect, useCallback, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import {
  XIcon,
  CheckCircleIcon,
  WarningCircleIcon,
  SpinnerGapIcon,
  ShoppingCartIcon,
  TagIcon,
} from '@phosphor-icons/react';
import { DESIGN_TOKENS, getWalletVerificationEvmChainId } from '@ledova/shared';
import { AnimatedQRCode } from '@keystonehq/animated-qr';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;
const ICON_HERO = DESIGN_TOKENS.icon.sizes.hero;
const ICON_DISPLAY = DESIGN_TOKENS.icon.sizes.display;
import { useQRScanner, QRScannerView } from '@components/qr';
import type {
  CreateOrderRequest,
  CreateOrderMessageResponse,
  CancelOrderMessageResponse,
  TransferOrder,
  Wallet,
} from '@ledova/shared';
import { encodeEthereumMessage } from '@utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '@utils/keystone/urDecoder';
import { signEthereumMessage, deriveAddress } from '@utils/softwareWallet/localSigner';
import { useOrderCreateMessage, useOrderCancelMessage, useCreateOrder, useCancelOrder } from '../useTrading';

type SigningMode = 'create' | 'cancel';

type SigningStep =
  'loading' | 'instructions' | 'show-qr' | 'scan-signature' | 'signing-software' | 'submitting' | 'success' | 'error';

interface OrderSigningFlowProps {
  isOpen: boolean;
  onClose: () => void;
  mode: SigningMode;

  orderData?: CreateOrderRequest;

  orderUuid?: string;
  orderSymbol?: string;

  wallet: Wallet | null;

  onSuccess?: (order: TransferOrder) => void;
}

export function OrderSigningFlow({
  isOpen,
  onClose,
  mode,
  orderData,
  orderUuid,
  orderSymbol,
  wallet,
  onSuccess,
}: OrderSigningFlowProps) {
  const [signingStep, setSigningStep] = useState<SigningStep>('loading');
  const [messageData, setMessageData] = useState<CreateOrderMessageResponse | CancelOrderMessageResponse | null>(null);
  const [qrData, setQrData] = useState<{ cborHex: string; type: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seedPhrase, setSeedPhrase] = useState('');

  const isSoftwareWallet = wallet?.walletType === 'software' || (!wallet?.derivationPath && !wallet?.masterFingerprint);

  const createMessageMutation = useOrderCreateMessage();
  const cancelMessageMutation = useOrderCancelMessage();
  const createOrderMutation = useCreateOrder();
  const cancelOrderMutation = useCancelOrder();

  const isCreating = mode === 'create';
  const isCancelling = mode === 'cancel';

  useEffect(() => {
    if (isOpen) {
      setSigningStep('loading');
      setMessageData(null);
      setQrData(null);
      setError(null);
      setSeedPhrase('');

      if (isCreating && orderData) {
        createMessageMutation.mutate(orderData, {
          onSuccess: (data) => {
            setMessageData(data);
            setSigningStep('instructions');
          },
          onError: (err) => {
            setError(err instanceof Error ? err.message : 'Failed to get signing message');
            setSigningStep('error');
          },
        });
      } else if (isCancelling && orderUuid) {
        cancelMessageMutation.mutate(orderUuid, {
          onSuccess: (data) => {
            setMessageData(data);
            setSigningStep('instructions');
          },
          onError: (err) => {
            setError(err instanceof Error ? err.message : 'Failed to get signing message');
            setSigningStep('error');
          },
        });
      }
    }
  }, [isOpen, mode, orderData, orderUuid]);

  const generateQrCode = useCallback(() => {
    if (!messageData || !wallet) {
      setError('Missing message data or wallet');
      setSigningStep('error');
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
      setError('Failed to encode message for signing');
      setSigningStep('error');
      return;
    }

    setQrData({ cborHex: encoded.cbor.toString('hex'), type: encoded.type });
    setSigningStep('show-qr');
  }, [messageData, wallet]);

  const handleContinue = useCallback(() => {
    if (isSoftwareWallet) {
      setSigningStep('signing-software');
    } else {
      generateQrCode();
    }
  }, [isSoftwareWallet, generateQrCode]);

  const handleSignatureScanned = useCallback(
    (signature: string) => {
      if (!messageData) return;

      setSigningStep('submitting');

      if (isCreating && orderData) {
        createOrderMutation.mutate(
          {
            ...orderData,
            message: messageData.message,
            signature,
          },
          {
            onSuccess: (order) => {
              setSigningStep('success');
              onSuccess?.(order);
            },
            onError: (err) => {
              setError(err instanceof Error ? err.message : 'Failed to create order');
              setSigningStep('error');
            },
          },
        );
      } else if (isCancelling && orderUuid) {
        cancelOrderMutation.mutate(
          {
            uuid: orderUuid,
            message: messageData.message,
            signature,
          },
          {
            onSuccess: (order) => {
              setSigningStep('success');
              onSuccess?.(order);
            },
            onError: (err) => {
              setError(err instanceof Error ? err.message : 'Failed to cancel order');
              setSigningStep('error');
            },
          },
        );
      }
    },
    [messageData, isCreating, isCancelling, orderData, orderUuid, createOrderMutation, cancelOrderMutation, onSuccess],
  );

  const handleSoftwareSign = useCallback(async () => {
    if (!messageData || !wallet?.derivationPath || !seedPhrase.trim()) return;

    try {
      const derivedAddr = deriveAddress(seedPhrase.trim(), wallet.derivationPath);
      if (derivedAddr.toLowerCase() !== wallet.address.toLowerCase()) {
        setError('Seed phrase does not match this wallet address');
        return;
      }

      setSigningStep('submitting');
      const signature = await signEthereumMessage(seedPhrase.trim(), wallet.derivationPath, messageData.message);
      setSeedPhrase('');
      handleSignatureScanned(signature);
    } catch (err) {
      setSeedPhrase('');
      setError(err instanceof Error ? err.message : 'Signing failed');
      setSigningStep('error');
    }
  }, [messageData, wallet, seedPhrase, handleSignatureScanned]);

  const { error: scannerError, stopScanner } = useQRScanner({
    scannerId: 'order-qr-scanner',
    onScanSuccess: (text) => {
      const decoded = decodeKeystoneMessageSignature(text);
      if (decoded) {
        handleSignatureScanned(decoded);
      }
    },
    enabled: signingStep === 'scan-signature',
  });

  const handleClose = useCallback(() => {
    if (signingStep === 'submitting') return;
    stopScanner();
    onClose();
  }, [onClose, signingStep, stopScanner]);

  useEffect(() => {
    if (signingStep === 'success') {
      const timer = setTimeout(() => {
        handleClose();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [signingStep, handleClose]);

  const goBack = useCallback(() => {
    if (signingStep === 'scan-signature') {
      setSigningStep('show-qr');
    } else if (signingStep === 'show-qr') {
      setSigningStep('instructions');
    } else if (signingStep === 'error') {
      setSigningStep('instructions');
      setError(null);
    }
  }, [signingStep]);

  const renderStepContent = () => {
    if (signingStep === 'loading') {
      return (
        <div className="flex flex-col items-center justify-center py-8 gap-3">
          <SpinnerGapIcon size={ICON_XL} className="text-brand-mid animate-spin" />
          <p className="text-sm text-text-muted">Preparing signing data...</p>
        </div>
      );
    }

    switch (signingStep) {
      case 'instructions':
        return (
          <div className="space-y-5">
            <p className="text-sm text-text-muted">
              {isCreating
                ? `Sign this order with your ${isSoftwareWallet ? 'seed phrase' : 'hardware wallet'} to authorize the trade.`
                : `Sign this cancellation with your ${isSoftwareWallet ? 'seed phrase' : 'hardware wallet'} to cancel your order.`}
            </p>

            {messageData && (
              <div className="bg-surface-tertiary rounded-lg p-4 space-y-2">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {isCreating && 'tokenUuid' in messageData && (
                    <>
                      <div className="text-text-muted">Type</div>
                      <div
                        className={`font-medium ${messageData.orderType === 'buy' ? 'text-success-light' : 'text-error-light'}`}
                      >
                        {messageData.orderType.toUpperCase()}
                      </div>
                      <div className="text-text-muted">Quantity</div>
                      <div className="text-text-primary">{messageData.quantity} shares</div>
                      <div className="text-text-muted">Price</div>
                      <div className="text-text-primary">${messageData.pricePerShare}</div>
                    </>
                  )}
                  {isCancelling && 'orderUuid' in messageData && (
                    <>
                      <div className="text-text-muted">Order</div>
                      <div className="text-text-primary font-mono text-xs">{messageData.orderUuid.slice(0, 8)}...</div>
                      {orderSymbol && (
                        <>
                          <div className="text-text-muted">Token</div>
                          <div className="text-text-primary">{orderSymbol}</div>
                        </>
                      )}
                    </>
                  )}
                </div>
              </div>
            )}

            {isSoftwareWallet ? (
              <div className="space-y-3">
                <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                  <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                    1
                  </span>
                  <p className="text-sm text-text-secondary">Enter your seed phrase to sign the message</p>
                </div>
                <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                  <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                    2
                  </span>
                  <p className="text-sm text-text-secondary">
                    Your seed phrase is used locally and never stored or transmitted
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                  <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                    1
                  </span>
                  <p className="text-sm text-text-secondary">Scan the QR code with your hardware wallet</p>
                </div>
                <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                  <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                    2
                  </span>
                  <p className="text-sm text-text-secondary">Review and sign the message on your hardware wallet</p>
                </div>
                <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                  <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                    3
                  </span>
                  <p className="text-sm text-text-secondary">Scan the signature QR code from your hardware wallet</p>
                </div>
              </div>
            )}

            {error && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{error}</p>
              </div>
            )}

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
                onClick={handleContinue}
                disabled={!messageData || !wallet}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Continue
              </button>
            </div>
          </div>
        );

      case 'show-qr':
        return (
          <div className="space-y-5">
            <p className="text-sm text-text-muted">
              Scan this QR code with your hardware wallet to sign the {isCreating ? 'order' : 'cancellation'}.
            </p>

            {qrData && (
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <AnimatedQRCode cbor={qrData.cborHex} type={qrData.type} />
              </div>
            )}

            {error && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{error}</p>
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
                onClick={() => setSigningStep('scan-signature')}
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
            <p className="text-sm text-text-muted">
              Point your camera at the signature QR code on your hardware wallet.
            </p>

            <QRScannerView scannerId="order-qr-scanner" error={scannerError} />

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

      case 'signing-software':
        return (
          <div className="space-y-5">
            <p className="text-sm text-text-muted">
              Enter the seed phrase for wallet{' '}
              <span className="font-mono text-xs text-text-secondary">
                {wallet?.address.slice(0, 6)}...{wallet?.address.slice(-4)}
              </span>
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

            {error && (
              <div className="p-3 bg-error/10 border border-error/20 rounded-lg">
                <p className="text-sm text-error">{error}</p>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={() => {
                  setSeedPhrase('');
                  setSigningStep('instructions');
                }}
                className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                onClick={handleSoftwareSign}
                disabled={!seedPhrase.trim() || !wallet?.derivationPath}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Sign
              </button>
            </div>
          </div>
        );

      case 'submitting':
        return (
          <div className="flex flex-col items-center justify-center py-8 gap-3">
            <SpinnerGapIcon size={ICON_XL} className="text-brand-mid animate-spin" />
            <p className="text-sm text-text-muted">{isCreating ? 'Creating order...' : 'Cancelling order...'}</p>
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
              <h3 className="text-xl font-semibold text-success mb-2">
                {isCreating ? 'Order Created!' : 'Order Cancelled!'}
              </h3>
              <p className="text-sm text-text-muted">
                {isCreating
                  ? 'Your order has been placed successfully.'
                  : 'Your order has been cancelled successfully.'}
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
              <h3 className="text-lg font-semibold text-text-primary">
                {isCreating ? 'Order Failed' : 'Cancellation Failed'}
              </h3>
              <p className="text-sm text-text-muted mt-1">{error || 'An error occurred'}</p>
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

  const modalTitle = isCreating ? 'Sign Order' : 'Cancel Order';
  const TitleIcon = isCreating ? ShoppingCartIcon : TagIcon;

  return (
    <Transition show={isOpen}>
      <Dialog onClose={handleClose} className="relative z-50">
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
                <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
                  <Dialog.Title className="text-lg font-semibold text-text-primary flex items-center gap-2">
                    <TitleIcon size={ICON_MD} className="text-brand-light" />
                    {modalTitle}
                  </Dialog.Title>
                  <button
                    onClick={handleClose}
                    disabled={signingStep === 'submitting'}
                    className="p-1 rounded-lg hover:bg-surface-tertiary transition-colors disabled:opacity-50"
                  >
                    <XIcon size={ICON_MD} className="text-text-muted" />
                  </button>
                </div>

                <div className="p-4">{renderStepContent()}</div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
