import { useEffect, useRef, useCallback, useState } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import {
  XIcon,
  CheckCircleIcon,
  WarningCircleIcon,
  SpinnerGapIcon,
  PaperPlaneTiltIcon,
  ArrowSquareOutIcon,
} from '@phosphor-icons/react';
import { AnimatedQRCode } from '@keystonehq/animated-qr';
import { formatWalletAddressMedium } from '@ledova/shared-utils';
import { BLOCKCHAIN, DESIGN_TOKENS, getBlockExplorerTxUrl, getChainShortCode } from '@ledova/shared-constants';
import { useQRScanner, QRScannerView } from '@components/qr';

const ICON_XS = DESIGN_TOKENS.icon.sizes.xs;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;
const ICON_HERO = DESIGN_TOKENS.icon.sizes.hero;
const ICON_DISPLAY = DESIGN_TOKENS.icon.sizes.display;
import type {
  Wallet,
  WalletTokenBalance,
  ShareTokenTransferPrepareResponse,
  PreparedWalletTransfer,
} from '@ledova/shared-types';
import { encodeEthereumTransaction } from '@utils/keystone/urEncoder';
import { decodeKeystoneSignedTransaction } from '@utils/keystone/urDecoder';
import { BitcoinSignStep } from './BitcoinSignStep';

export type TransferType = 'crypto' | 'stablecoin' | 'share_token';

type SigningStep =
  'loading' | 'instructions' | 'show-qr' | 'scan-signature' | 'sign-manual' | 'submitting' | 'success' | 'error';

interface TransferSigningFlowProps {
  isOpen: boolean;
  onClose: () => void;
  transferType: TransferType;
  wallet: Wallet;
  toAddress?: string;
  amount?: string;
  token?: WalletTokenBalance;
  preparedTransaction?: ShareTokenTransferPrepareResponse | PreparedWalletTransfer | null;
  isPreparing?: boolean;
  prepareError?: string | null;
  onPrepare?: () => void;
  onBroadcast?: (signedTx: string) => Promise<string>;
  onSuccess?: (txHash: string) => void;
}

interface TransactionForQr {
  to: string;
  from: string;
  data: string;
  value: string;
  gas: string;
  gasPrice: string;
  nonce: string;
  chainId: string;
}

function formatTransactionForQr(
  preparedTx: ShareTokenTransferPrepareResponse | PreparedWalletTransfer,
  wallet: Wallet,
): TransactionForQr | null {
  if ('transactionData' in preparedTx && preparedTx.transactionData) {
    const tx = preparedTx.transactionData;
    return {
      to: tx.to,
      from: wallet.address,
      data: tx.data,
      value: '0x' + tx.value.toString(16),
      gas: '0x' + tx.gas.toString(16),
      gasPrice: '0x' + tx.gasPrice.toString(16),
      nonce: '0x' + tx.nonce.toString(16),
      chainId: '0x' + tx.chainId.toString(16),
    };
  }

  if ('transaction' in preparedTx && preparedTx.transaction) {
    const tx = preparedTx.transaction;
    const gasPrice = tx.gasPrice ?? tx.maxFeePerGas ?? 0;
    return {
      to: tx.to,
      from: wallet.address,
      data: tx.data || '0x',
      value: '0x' + tx.value.toString(16),
      gas: '0x' + tx.gas.toString(16),
      gasPrice: '0x' + gasPrice.toString(16),
      nonce: '0x' + tx.nonce.toString(16),
      chainId: '0x' + tx.chainId.toString(16),
    };
  }

  return null;
}

export function TransferSigningFlow({
  isOpen,
  onClose,
  transferType,
  wallet,
  toAddress,
  amount,
  token,
  preparedTransaction,
  isPreparing = false,
  prepareError = null,
  onPrepare,
  onBroadcast,
  onSuccess,
}: TransferSigningFlowProps) {
  const [signingStep, setSigningStep] = useState<SigningStep>('loading');
  const [qrData, setQrData] = useState<{ cborHex: string; type: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [txHash, setTxHash] = useState<string | null>(null);
  const [unsignedTx, setUnsignedTx] = useState<TransactionForQr | null>(null);
  const [signedTransaction, setSignedTransaction] = useState('');

  const isBitcoin = wallet.chain === BLOCKCHAIN.BITCOIN;
  const nativeSymbol = getChainShortCode(wallet.chain);

  const hasPreparedRef = useRef(false);
  const onPrepareRef = useRef(onPrepare);

  useEffect(() => {
    onPrepareRef.current = onPrepare;
  }, [onPrepare]);

  const getTitle = () => {
    switch (transferType) {
      case 'crypto':
        return 'Sign Transfer';
      case 'stablecoin':
        return 'Sign Stablecoin Transfer';
      case 'share_token':
        return 'Sign Token Transfer';
      default:
        return 'Sign Transfer';
    }
  };

  useEffect(() => {
    if (isOpen) {
      setSigningStep('loading');
      setQrData(null);
      setError(null);
      setTxHash(null);
      setUnsignedTx(null);
      setSignedTransaction('');

      if (!hasPreparedRef.current && onPrepareRef.current) {
        hasPreparedRef.current = true;
        onPrepareRef.current();
      }
    } else {
      hasPreparedRef.current = false;
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && preparedTransaction && signingStep === 'loading') {
      setSigningStep(isBitcoin ? 'sign-manual' : 'instructions');
    }
  }, [isOpen, preparedTransaction, signingStep, isBitcoin]);

  useEffect(() => {
    if (isOpen && prepareError && signingStep === 'loading') {
      setError(prepareError);
      setSigningStep('error');
    }
  }, [isOpen, prepareError, signingStep]);

  const generateQrCode = useCallback(() => {
    if (!preparedTransaction || !wallet) {
      setError('Missing transaction data or wallet');
      setSigningStep('error');
      return;
    }

    const txForQr = formatTransactionForQr(preparedTransaction, wallet);
    if (!txForQr) {
      setError('Failed to format transaction for signing');
      setSigningStep('error');
      return;
    }

    setUnsignedTx(txForQr);

    const encoded = encodeEthereumTransaction(
      txForQr,
      wallet.derivationPath || undefined,
      wallet.masterFingerprint || undefined,
    );

    if (!encoded) {
      setError('Failed to encode transaction for signing. Make sure wallet has derivation path and fingerprint.');
      setSigningStep('error');
      return;
    }

    setQrData({ cborHex: encoded.cborHex, type: encoded.type });
    setSigningStep('show-qr');
  }, [preparedTransaction, wallet]);

  const submitSignedTransaction = useCallback(
    async (signedTransactionHex: string) => {
      if (!onBroadcast) return;

      setSigningStep('submitting');

      try {
        const hash = await onBroadcast(signedTransactionHex);
        setTxHash(hash);
        setSigningStep('success');
        onSuccess?.(hash);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to broadcast transaction');
        setSigningStep('error');
      }
    },
    [onBroadcast, onSuccess],
  );

  const { error: scannerError, stopScanner } = useQRScanner({
    scannerId: 'transfer-qr-scanner',
    onScanSuccess: (text) => {
      const signedTx = decodeKeystoneSignedTransaction(
        text,
        unsignedTx
          ? {
              to: unsignedTx.to,
              value: unsignedTx.value,
              gas: unsignedTx.gas,
              gasPrice: unsignedTx.gasPrice,
              nonce: unsignedTx.nonce,
              data: unsignedTx.data,
              chainId: unsignedTx.chainId,
            }
          : undefined,
      );
      if (signedTx) {
        submitSignedTransaction(signedTx);
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
    if (signingStep === 'success' && !isBitcoin) {
      const timer = setTimeout(() => {
        handleClose();
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [signingStep, handleClose, isBitcoin]);

  const goBack = useCallback(() => {
    if (signingStep === 'scan-signature') {
      setSigningStep('show-qr');
    } else if (signingStep === 'show-qr') {
      setSigningStep('instructions');
    } else if (signingStep === 'error') {
      setSigningStep(isBitcoin ? 'sign-manual' : 'instructions');
      setError(null);
    }
  }, [signingStep, isBitcoin]);

  const renderStepContent = () => {
    if (signingStep === 'loading' || isPreparing) {
      return (
        <div className="flex flex-col items-center justify-center py-8 gap-3">
          <SpinnerGapIcon size={ICON_XL} className="text-brand-mid animate-spin" />
          <p className="text-sm text-text-muted">Preparing transaction...</p>
        </div>
      );
    }

    switch (signingStep) {
      case 'instructions':
        return (
          <div className="space-y-5">
            <p className="text-sm text-text-muted">
              Sign this transfer with your hardware wallet to authorize the transaction.
            </p>

            <div className="bg-surface-tertiary rounded-lg p-4 space-y-2">
              <div className="grid grid-cols-2 gap-2 text-sm">
                {token && (
                  <>
                    <div className="text-text-muted">Token</div>
                    <div className="text-text-primary font-medium">
                      {token.symbol} ({token.name})
                    </div>
                  </>
                )}
                <div className="text-text-muted">From</div>
                <div className="text-text-primary font-mono text-xs">{formatWalletAddressMedium(wallet.address)}</div>
                {toAddress && (
                  <>
                    <div className="text-text-muted">To</div>
                    <div className="text-text-primary font-mono text-xs">{formatWalletAddressMedium(toAddress)}</div>
                  </>
                )}
                {amount && (
                  <>
                    <div className="text-text-muted">Amount</div>
                    <div className="text-text-primary font-medium">
                      {amount} {token?.symbol ?? nativeSymbol}
                    </div>
                  </>
                )}
              </div>
            </div>

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
                <p className="text-sm text-text-secondary">Review and sign the transaction on your hardware wallet</p>
              </div>
              <div className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
                <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
                  3
                </span>
                <p className="text-sm text-text-secondary">Scan the signature QR code from your hardware wallet</p>
              </div>
            </div>

            {error && (
              <div className="p-3 bg-error-light/10 border border-error-light/20 rounded-lg">
                <p className="text-sm text-error-light">{error}</p>
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
                onClick={generateQrCode}
                disabled={!preparedTransaction || !wallet}
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
            <p className="text-sm text-text-muted">Scan this QR code with your hardware wallet to sign the transfer.</p>

            {qrData && (
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <AnimatedQRCode cbor={qrData.cborHex} type={qrData.type} />
              </div>
            )}

            {error && (
              <div className="p-3 bg-error-light/10 border border-error-light/20 rounded-lg">
                <p className="text-sm text-error-light">{error}</p>
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

      case 'sign-manual':
        if (!preparedTransaction || !('amountBtc' in preparedTransaction)) return null;
        return (
          <BitcoinSignStep
            prepared={preparedTransaction}
            signedTransaction={signedTransaction}
            onSignedTransactionChange={setSignedTransaction}
            onCancel={handleClose}
            onBroadcast={submitSignedTransaction}
          />
        );

      case 'scan-signature':
        return (
          <div className="space-y-5">
            <p className="text-sm text-text-muted">
              Point your camera at the signature QR code on your hardware wallet.
            </p>

            <QRScannerView scannerId="transfer-qr-scanner" error={scannerError} />

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
            <p className="text-sm text-text-muted">Broadcasting transaction...</p>
            <p className="text-xs text-text-subtle">This may take a moment</p>
          </div>
        );

      case 'success': {
        const explorerUrl = txHash ? getBlockExplorerTxUrl(wallet.chain, txHash) : '';
        return (
          <div className="space-y-6 py-8">
            <div className="flex justify-center">
              <div className="p-4 bg-success-light/10 rounded-full">
                <CheckCircleIcon size={ICON_DISPLAY} className="text-success-light" weight="fill" />
              </div>
            </div>

            <div className="text-center">
              <h3 className="text-xl font-semibold text-success-light mb-2">Transfer Sent!</h3>
              <p className="text-sm text-text-muted">Your transaction has been submitted to the network.</p>
            </div>

            {txHash && (
              <div className="p-4 rounded-lg bg-surface-tertiary border border-border">
                <p className="text-xs font-semibold text-text-subtle uppercase tracking-wide mb-2">Transaction Hash</p>
                <p className="text-xs font-mono text-text-primary break-all">{txHash}</p>
                {explorerUrl && (
                  <a
                    href={explorerUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-brand-mid hover:text-brand-light"
                  >
                    View on block explorer
                    <ArrowSquareOutIcon size={ICON_XS} />
                  </a>
                )}
              </div>
            )}

            {isBitcoin && (
              <button
                type="button"
                onClick={handleClose}
                className="w-full py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand transition-colors"
              >
                Done
              </button>
            )}
          </div>
        );
      }

      case 'error':
        return (
          <div className="flex flex-col items-center justify-center py-8 gap-4">
            <div className="w-16 h-16 rounded-full bg-error-light/10 flex items-center justify-center">
              <WarningCircleIcon size={ICON_HERO} className="text-error-light" weight="fill" />
            </div>
            <div className="text-center">
              <h3 className="text-lg font-semibold text-text-primary">Transfer Failed</h3>
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
                    <PaperPlaneTiltIcon size={ICON_MD} className="text-brand-light" />
                    {getTitle()}
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
