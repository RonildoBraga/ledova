import { useEffect, useRef, useState } from 'react';
import { AnimatedQRCode } from '@keystonehq/animated-qr';
import {
  getWalletVerificationEvmChainId,
  useOrderSubmissionSigning,
  type OrderSubmission,
  type TransferOrder,
  type Wallet,
  type ShareToken,
  formatWalletAddressShort,
} from '@ledova/shared';
import { Modal } from '@components/Modal';
import { SeedPhraseInput } from '@components/SeedPhraseInput';
import { QRScannerView, useQRScanner } from '@components/qr';
import { encodeEthereumTypedData } from '@utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '@utils/keystone/urDecoder';
import { deriveAddress, signEthereumTypedData } from '@utils/softwareWallet/localSigner';

interface Props {
  submission: OrderSubmission;
  wallet: Wallet | null;
  tokens: ShareToken[];
  onClose: () => void;
  onSuccess?: (order: TransferOrder, recovered?: boolean) => void;
}

export function CreateOrderSigningFlow({ submission, wallet, tokens, onClose, onSuccess }: Props) {
  const [seedPhrase, setSeedPhrase] = useState('');
  const delivered = useRef(false);
  const signing = useOrderSubmissionSigning(submission, wallet, (message, selectedWallet) => {
    const encoded = encodeEthereumTypedData(
      selectedWallet.address,
      { domain: message.domain, types: message.types, message: message.message },
      selectedWallet.derivationPath || undefined,
      selectedWallet.masterFingerprint || undefined,
      getWalletVerificationEvmChainId(selectedWallet.chain) ?? undefined,
    );
    return encoded ? { cborHex: encoded.cbor.toString('hex'), type: encoded.type } : null;
  });
  const { state, view } = signing;
  const token = tokens.find((candidate) => candidate.uuid === state.snapshot?.intent.token);
  const software = wallet?.signingPreference === 'software' || (!wallet?.derivationPath && !wallet?.masterFingerprint);
  const { error: scannerError, stopScanner } = useQRScanner({
    scannerId: 'create-order-signature',
    enabled: state.phase === 'ready' && view.step === 'scan-signature',
    onScanSuccess: (text) => {
      const signature = decodeKeystoneMessageSignature(text);
      if (signature) void signing.submitSignature(signature);
    },
  });
  useEffect(() => {
    if (state.phase === 'created' && state.snapshot?.order && !delivered.current && submission.isCurrent()) {
      delivered.current = true;
      onSuccess?.(state.snapshot.order, state.recovered);
    }
  }, [state, submission, onSuccess]);
  const close = () => {
    signing.close();
    stopScanner();
    setSeedPhrase('');
    onClose();
  };
  const sign = () => {
    const phrase = seedPhrase.trim();
    setSeedPhrase('');
    void signing.sign(async (message, current) => {
      if (!phrase || !wallet?.derivationPath || !current()) return null;
      if (deriveAddress(phrase, wallet.derivationPath).toLowerCase() !== wallet.address.toLowerCase()) {
        throw new Error('Seed phrase does not match this wallet address.');
      }
      if (!current()) return null;
      return signEthereumTypedData(phrase, wallet.derivationPath, message.domain, message.types, message.message);
    });
  };
  const button = 'rounded-lg bg-brand-mid px-4 py-3 font-medium text-white disabled:opacity-50';
  return (
    <Modal isOpen onClose={close} title={state.recovered ? 'Check saved order' : 'Review order'} size="md">
      <div className="space-y-4">
        {state.phase === 'preparing' && <p>Checking order and preparing signing details...</p>}
        {state.phase === 'signing' && <p>Signing this order...</p>}
        {state.phase === 'submitting' && (
          <p>Submitting this order. You can close this window and check its status from saved orders.</p>
        )}
        {state.phase === 'ready' && (
          <>
            <div className="rounded-lg bg-surface-tertiary p-4 space-y-2">
              <p>Token: {token ? `${token.symbol} — ${token.name}` : state.snapshot?.intent.token}</p>
              <p>Wallet: {formatWalletAddressShort(state.snapshot?.intent.walletAddress ?? '')}</p>
              <p>
                {state.snapshot?.intent.orderType.toUpperCase()} {state.snapshot?.intent.quantity} shares
              </p>
              <p>Price per share: ${state.snapshot?.intent.pricePerShare}</p>
              <p>Minimum fill: {state.snapshot?.intent.minQuantity} shares</p>
            </div>
            {!signing.walletReady && (
              <p>
                This wallet is unavailable for signing in the current account. The saved order remains available to
                check.
              </p>
            )}
            {view.error && <p role="alert">{view.error}</p>}
            {view.step === 'instructions' && (
              <button
                className={button}
                disabled={!signing.walletReady}
                onClick={software ? signing.showSoftware : signing.showQr}
              >
                Continue to sign
              </button>
            )}
            {view.step === 'software' && (
              <>
                <SeedPhraseInput value={seedPhrase} onChange={setSeedPhrase} />
                <button className={button} disabled={!seedPhrase.trim() || !wallet?.derivationPath} onClick={sign}>
                  Sign order
                </button>
              </>
            )}
            {view.step === 'show-qr' && view.qrData && (
              <>
                <div className="flex justify-center bg-white p-4">
                  <AnimatedQRCode cbor={view.qrData.cborHex} type={view.qrData.type} />
                </div>
                <button className={button} onClick={signing.scan}>
                  I&apos;ve signed it
                </button>
              </>
            )}
            {view.step === 'scan-signature' && (
              <QRScannerView scannerId="create-order-signature" error={scannerError} />
            )}
            {view.step !== 'instructions' && (
              <button
                className={button}
                onClick={() => {
                  setSeedPhrase('');
                  signing.back();
                }}
              >
                Back
              </button>
            )}
          </>
        )}
        {state.phase === 'created' && state.snapshot?.order && (
          <div role="status" className="space-y-2">
            <h3>{state.recovered ? 'Order recovered' : 'Order created'}</h3>
            <p>
              Current status: {state.snapshot.order.statusDisplay ?? state.snapshot.order.status.replace(/_/g, ' ')}
            </p>
            <p>
              {state.snapshot.order.quantity} {state.snapshot.order.tokenSymbol} shares at $
              {state.snapshot.order.pricePerShare}
            </p>
          </div>
        )}
        {state.phase === 'refused' && (
          <div role="status">
            <h3>Order declined</h3>
            <p>{state.snapshot?.refusal?.detail}</p>
            <p>A new order requires a new review and signature.</p>
          </div>
        )}
        {state.phase === 'error' && (
          <div role="alert" className="space-y-3">
            <h3>Order status unconfirmed</h3>
            <p>{state.error}</p>
            <p>
              This order remains saved. Check its status before signing again. An unavailable result does not start a
              replacement order.
            </p>
            <button className={button} onClick={() => void submission.recover()}>
              Check order status
            </button>
          </div>
        )}
        {state.notice && <p>{state.notice}</p>}
        <button className="rounded-lg bg-surface-tertiary px-4 py-3" onClick={close}>
          {['created', 'refused'].includes(state.phase) ? 'Done' : 'Close'}
        </button>
      </div>
    </Modal>
  );
}
