/**
 * OrderModificationModal Component
 * Modal for modifying open orders with hardware wallet signing.
 * Follows the two-step flow: generate message → sign → execute.
 */

import { useEffect, useCallback, useState, useMemo } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import {
  XIcon,
  CheckCircleIcon,
  WarningCircleIcon,
  SpinnerGapIcon,
  PencilSimpleIcon,
  InfoIcon,
} from '@phosphor-icons/react';
import { DESIGN_TOKENS, getWalletVerificationEvmChainId } from '@ledova/shared-constants';
import { AnimatedQRCode } from '@keystonehq/animated-qr';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;
const ICON_HERO = DESIGN_TOKENS.icon.sizes.hero;
const ICON_DISPLAY = DESIGN_TOKENS.icon.sizes.display;
import { useQRScanner, QRScannerView } from '@components/qr';
import type { Wallet, TransferOrder } from '@ledova/shared-types';
import { formatCurrency } from '@ledova/shared-utils';
import { encodeEthereumMessage } from '@utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '@utils/keystone/urDecoder';
import {
  useOrderModificationMessage,
  useExecuteOrderModification,
  parseTradingError,
  type OrderModificationRequest,
  type OrderModificationMessageResponse,
} from '../useTrading';

type ModificationStep =
  'form' | 'loading' | 'instructions' | 'show-qr' | 'scan-signature' | 'submitting' | 'success' | 'error';

interface OrderModificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  order: TransferOrder | null;
  wallet: Wallet | null;
  onSuccess?: (order: TransferOrder) => void;
}

export function OrderModificationModal({ isOpen, onClose, order, wallet, onSuccess }: OrderModificationModalProps) {
  // Form state
  const [newQuantity, setNewQuantity] = useState('');
  const [newMinQuantity, setNewMinQuantity] = useState('');
  const [newPricePerShare, setNewPricePerShare] = useState('');

  // Flow state
  const [step, setStep] = useState<ModificationStep>('form');
  const [messageData, setMessageData] = useState<OrderModificationMessageResponse | null>(null);
  const [qrData, setQrData] = useState<{ cborHex: string; type: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Mutations
  const modificationMessageMutation = useOrderModificationMessage();
  const executeModificationMutation = useExecuteOrderModification();

  // Reset form when modal opens with new order
  useEffect(() => {
    if (isOpen && order) {
      setNewQuantity(order.quantity.toString());
      setNewMinQuantity(order.minQuantity?.toString() || '0');
      setNewPricePerShare(order.pricePerShare);
      setStep('form');
      setMessageData(null);
      setQrData(null);
      setError(null);
    }
  }, [isOpen, order]);

  // Parse order details
  const orderDetails = useMemo(() => {
    if (!order) return null;

    const filledQuantity = order.filledQuantity || 0;
    const remainingQuantity = order.quantity - filledQuantity;
    const minQuantity = order.minQuantity || 0;

    return {
      filledQuantity,
      remainingQuantity,
      minQuantity,
    };
  }, [order]);

  // Calculate quantity change details
  const quantityChange = useMemo(() => {
    if (!order || !orderDetails) return null;

    const newQty = parseInt(newQuantity, 10) || 0;
    const currentQty = order.quantity;
    const delta = newQty - currentQty;
    const newRemaining = newQty - orderDetails.filledQuantity;

    return {
      currentQty,
      newQty,
      delta,
      newRemaining,
      hasChanged: delta !== 0,
    };
  }, [order, orderDetails, newQuantity]);

  // Validate form
  const formValidation = useMemo(() => {
    if (!order || !orderDetails) return { isValid: false, hasChanges: false, errors: [] as string[] };

    const errors: string[] = [];
    const qty = parseInt(newQuantity, 10) || 0;
    const minQty = parseInt(newMinQuantity, 10) || 0;
    const price = parseFloat(newPricePerShare) || 0;

    // Quantity must exceed filled amount
    if (qty <= orderDetails.filledQuantity) {
      errors.push(`Quantity must be greater than filled amount (${orderDetails.filledQuantity})`);
    }

    // Min quantity must be achievable
    const newRemaining = qty - orderDetails.filledQuantity;
    if (minQty > newRemaining) {
      errors.push(`Min quantity (${minQty}) cannot exceed remaining (${newRemaining})`);
    }

    if (minQty < 0) {
      errors.push('Min quantity cannot be negative');
    }

    if (price <= 0) {
      errors.push('Price must be positive');
    }

    // Check if anything changed
    const hasChanges =
      qty !== order.quantity || minQty !== (order.minQuantity || 0) || price !== parseFloat(order.pricePerShare);

    return { isValid: errors.length === 0 && hasChanges, hasChanges, errors };
  }, [order, orderDetails, newQuantity, newMinQuantity, newPricePerShare]);

  // Handle form submission - generate modification message
  const handleFormSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!order || !formValidation.isValid) return;

      setStep('loading');
      setError(null);

      const modifications: OrderModificationRequest = {};

      const qty = parseInt(newQuantity, 10);
      if (qty !== order.quantity) {
        modifications.newQuantity = qty;
      }

      const minQty = parseInt(newMinQuantity, 10);
      if (minQty !== (order.minQuantity || 0)) {
        modifications.newMinQuantity = minQty;
      }

      const price = parseFloat(newPricePerShare);
      if (price !== parseFloat(order.pricePerShare)) {
        modifications.newPricePerShare = newPricePerShare;
      }

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
    },
    [order, formValidation.isValid, newQuantity, newMinQuantity, newPricePerShare, modificationMessageMutation],
  );

  // Generate QR code for signing
  const generateQrCode = useCallback(() => {
    if (!messageData || !wallet) {
      setError('Missing message data or wallet');
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
      setError('Failed to encode message for signing');
      setStep('error');
      return;
    }

    setQrData({ cborHex: encoded.cbor.toString('hex'), type: encoded.type });
    setStep('show-qr');
  }, [messageData, wallet]);

  // Handle signature scanned
  const handleSignatureScanned = useCallback(
    (signature: string) => {
      if (!messageData || !order) return;

      setStep('submitting');

      executeModificationMutation.mutate(
        {
          orderUuid: order.uuid,
          data: {
            message: messageData.message,
            signature,
          },
        },
        {
          onSuccess: (result) => {
            setStep('success');
            onSuccess?.(result.order);
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

  const { error: scannerError, stopScanner } = useQRScanner({
    scannerId: 'modify-qr-scanner',
    onScanSuccess: (text) => {
      const decoded = decodeKeystoneMessageSignature(text);
      if (decoded) {
        handleSignatureScanned(decoded);
      }
    },
    enabled: step === 'scan-signature',
  });

  // Handle modal close
  const handleClose = useCallback(() => {
    if (step === 'submitting') return;
    stopScanner();
    onClose();
  }, [onClose, step, stopScanner]);

  // Auto-close on success
  useEffect(() => {
    if (step === 'success') {
      const timer = setTimeout(() => {
        handleClose();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [step, handleClose]);

  const goBack = useCallback(() => {
    if (step === 'scan-signature') {
      setStep('show-qr');
    } else if (step === 'show-qr') {
      setStep('instructions');
    } else if (step === 'instructions') {
      setStep('form');
    } else if (step === 'error') {
      setStep('form');
      setError(null);
    }
  }, [step]);

  const renderStepContent = () => {
    if (!order || !orderDetails) return null;

    switch (step) {
      case 'form': {
        const totalValue = (parseInt(newQuantity, 10) || 0) * (parseFloat(newPricePerShare) || 0);

        return (
          <form onSubmit={handleFormSubmit} className="space-y-5">
            {/* Order Details */}
            <div className="space-y-0">
              <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
                <span className="text-sm text-text-muted">Filled:</span>
                <span className="text-sm font-medium text-text-primary">{orderDetails.filledQuantity} shares</span>
              </div>
              <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
                <span className="text-sm text-text-muted">Remaining:</span>
                <span className="text-sm font-medium text-text-primary">{orderDetails.remainingQuantity} shares</span>
              </div>
              <div className="flex items-center justify-between py-2.5 border-b border-border-subtle">
                <span className="text-sm text-text-muted">Total Value:</span>
                <span className={`text-sm font-semibold ${totalValue > 0 ? 'text-text-primary' : 'text-text-muted'}`}>
                  {formatCurrency(totalValue)}
                </span>
              </div>
            </div>

            {/* Form Inputs */}
            <div className="space-y-4 pt-2">
              {/* Quantity */}
              <div className="space-y-2">
                <label htmlFor="modify-quantity" className="text-sm font-medium text-text-primary">
                  Total Quantity (shares)
                </label>
                <input
                  id="modify-quantity"
                  type="number"
                  min={orderDetails.filledQuantity + 1}
                  step="1"
                  value={newQuantity}
                  onChange={(e) => setNewQuantity(e.target.value)}
                  placeholder="Enter total number of shares"
                  className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
                />
                {/* Quantity change summary */}
                {quantityChange && quantityChange.hasChanged && quantityChange.newRemaining > 0 && (
                  <div className="flex items-center justify-between text-xs text-text-muted">
                    <span>
                      {order.quantity} → {quantityChange.newQty}
                      <span
                        className={`ml-1 font-medium ${quantityChange.delta > 0 ? 'text-success-light' : 'text-error-light'}`}
                      >
                        ({quantityChange.delta > 0 ? '+' : ''}
                        {quantityChange.delta} shares)
                      </span>
                    </span>
                    <span>
                      New remaining:{' '}
                      <span className="font-medium text-text-secondary">{quantityChange.newRemaining}</span>
                    </span>
                  </div>
                )}
                <p className="text-xs text-text-muted">
                  Hint: Must be greater than filled amount ({orderDetails.filledQuantity})
                </p>
              </div>

              {/* Min Quantity */}
              <div className="space-y-2">
                <label htmlFor="modify-min-quantity" className="text-sm font-medium text-text-primary">
                  Minimum Fill Quantity (optional)
                </label>
                <input
                  id="modify-min-quantity"
                  type="number"
                  min="0"
                  step="1"
                  value={newMinQuantity}
                  onChange={(e) => setNewMinQuantity(e.target.value)}
                  placeholder="0 = accept any partial fill"
                  className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
                />
                <p className="text-xs text-text-muted">Hint: Leave empty or 0 to accept any partial fill</p>
              </div>

              {/* Price */}
              <div className="space-y-2">
                <label htmlFor="modify-price" className="text-sm font-medium text-text-primary">
                  Price per Share (AUD)
                </label>
                <input
                  id="modify-price"
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={newPricePerShare}
                  onChange={(e) => setNewPricePerShare(e.target.value)}
                  placeholder="Enter price per share"
                  className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
                />
              </div>
            </div>

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
                type="submit"
                disabled={!formValidation.isValid}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Continue
              </button>
            </div>
          </form>
        );
      }

      case 'loading':
        return (
          <div className="flex flex-col items-center justify-center py-8 gap-3">
            <SpinnerGapIcon size={ICON_XL} className="text-brand-mid animate-spin" />
            <p className="text-sm text-text-muted">Preparing modification...</p>
          </div>
        );

      case 'instructions':
        return (
          <div className="space-y-5">
            {/* Description */}
            <p className="text-sm text-text-muted">
              Sign this modification with your hardware wallet to authorize the changes.
            </p>

            {/* Changes Summary */}
            {messageData && (
              <div className="bg-surface-tertiary rounded-lg p-4 space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                  <InfoIcon size={ICON_SM} className="text-brand-light" />
                  Changes to Apply
                </div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {messageData.newValues.quantity !== messageData.currentValues.quantity && (
                    <>
                      <div className="text-text-muted">Quantity</div>
                      <div className="text-text-primary">
                        {messageData.currentValues.quantity} → {messageData.newValues.quantity}
                      </div>
                    </>
                  )}
                  {messageData.newValues.minQuantity !== messageData.currentValues.minQuantity && (
                    <>
                      <div className="text-text-muted">Min Quantity</div>
                      <div className="text-text-primary">
                        {messageData.currentValues.minQuantity} → {messageData.newValues.minQuantity}
                      </div>
                    </>
                  )}
                  {messageData.newValues.pricePerShare !== messageData.currentValues.pricePerShare && (
                    <>
                      <div className="text-text-muted">Price</div>
                      <div className="text-text-primary">
                        ${messageData.currentValues.pricePerShare} → ${messageData.newValues.pricePerShare}
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* Instructions */}
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
                onClick={generateQrCode}
                disabled={!messageData || !wallet}
                className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Show QR Code
              </button>
            </div>
          </div>
        );

      case 'show-qr':
        return (
          <div className="space-y-5">
            {/* Description */}
            <p className="text-sm text-text-muted">
              Scan this QR code with your hardware wallet to sign the modification.
            </p>

            {qrData && (
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <AnimatedQRCode cbor={qrData.cborHex} type={qrData.type} />
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
                onClick={() => setStep('scan-signature')}
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

            <QRScannerView scannerId="modify-qr-scanner" error={scannerError} />

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

      case 'submitting':
        return (
          <div className="flex flex-col items-center justify-center py-8 gap-3">
            <SpinnerGapIcon size={ICON_XL} className="text-brand-mid animate-spin" />
            <p className="text-sm text-text-muted">Applying modification...</p>
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
              <h3 className="text-xl font-semibold text-success mb-2">Order Modified!</h3>
              <p className="text-sm text-text-muted">Your order has been updated successfully.</p>
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
              <h3 className="text-lg font-semibold text-text-primary">Modification Failed</h3>
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
                    <PencilSimpleIcon size={ICON_MD} className="text-brand-light" />
                    {order ? (
                      <div className="flex items-baseline gap-2">
                        <span className="text-brand-light">{order.tokenSymbol}</span>
                        <span className="text-sm text-text-muted font-normal">·</span>
                        <span className="text-sm text-text-muted font-normal">{order.tokenName || 'Shares'}</span>
                      </div>
                    ) : (
                      'Modify Order'
                    )}
                  </Dialog.Title>
                  <button
                    onClick={handleClose}
                    disabled={step === 'submitting'}
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
