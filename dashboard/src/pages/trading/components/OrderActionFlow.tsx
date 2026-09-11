import { useState } from 'react';
import { AnimatedQRCode } from '@keystonehq/animated-qr';
import { useOrderActionSigning, type OrderAction, type Wallet } from '@ledova/shared';
import { Modal } from '@components/Modal';
import { SeedPhraseInput } from '@components/SeedPhraseInput';
import { QRScannerView, useQRScanner } from '@components/qr';
import { encodeEthereumTypedData } from '@utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '@utils/keystone/urDecoder';
import { deriveAddress, signEthereumTypedData } from '@utils/softwareWallet/localSigner';

interface Props {
  action: OrderAction;
  wallets: Wallet[];
  onClose: () => void;
}

export function OrderActionFlow({ action, wallets, onClose }: Props) {
  const [seedPhrase, setSeedPhrase] = useState('');
  const signing = useOrderActionSigning(action, wallets, (message, wallet) => {
    const encoded = encodeEthereumTypedData(
      wallet.address,
      { domain: message.domain, types: message.types, message: message.message },
      wallet.derivationPath || undefined,
      wallet.masterFingerprint || undefined,
      message.domain.chainId,
    );
    return encoded ? { cborHex: encoded.cbor.toString('hex'), type: encoded.type } : null;
  });
  const { state, view, wallet } = signing;
  const cancelling = action.purpose === 'cancel';
  const label = cancelling ? 'cancellation' : 'change';
  const software = wallet?.signingPreference === 'software' || (!wallet?.derivationPath && !wallet?.masterFingerprint);
  const { error: scannerError, stopScanner } = useQRScanner({
    scannerId: 'order-action-signature',
    enabled: state.phase === 'ready' && view.step === 'scan-signature',
    onScanSuccess: (text) => {
      const signature = decodeKeystoneMessageSignature(text);
      if (signature) void signing.submitSignature(signature);
    },
  });
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
      if (deriveAddress(phrase, wallet.derivationPath).toLowerCase() !== wallet.address.toLowerCase())
        throw new Error('Seed phrase does not match this wallet address.');
      if (!current()) return null;
      return signEthereumTypedData(phrase, wallet.derivationPath, message.domain, message.types, message.message);
    });
  };
  const review = state.snapshot?.review ?? state.context;
  const replacements = state.snapshot?.intent.modifications;
  const button = 'rounded-lg bg-brand-mid px-4 py-3 font-medium text-white disabled:opacity-50';
  return (
    <Modal isOpen onClose={close} title={cancelling ? 'Cancel order' : 'Change order'} size="md">
      <div className="space-y-4">
        {state.phase === 'loading' && <p>Loading current order details...</p>}
        {state.phase === 'preparing' && <p>Checking this {label} and preparing signing details...</p>}
        {state.phase === 'signing' && <p>Signing this {label}...</p>}
        {state.phase === 'submitting' && (
          <p>Submitting this {label}. You can close and check its saved status later.</p>
        )}
        {review && (
          <div className="rounded-lg bg-surface-tertiary p-4 space-y-2">
            <p>
              Token: {review.token.symbol} — {review.token.name}
            </p>
            <p>Wallet: {state.snapshot?.walletAddress ?? state.context?.walletAddress}</p>
            <p>Reviewed quantity: {review.currentValues.quantity} shares</p>
            <p>Reviewed minimum: {review.currentValues.minQuantity} shares</p>
            <p>Reviewed price per share: ${review.currentValues.pricePerShare}</p>
            <p>Filled: {review.currentValues.filledQuantity} shares</p>
          </div>
        )}
        {state.phase === 'editing' && (
          <>
            {cancelling ? (
              <p>Cancel the available remainder of this order.</p>
            ) : (
              <>
                <label className="block">
                  New quantity
                  <input
                    className="block w-full rounded-lg border p-2"
                    inputMode="numeric"
                    value={state.values?.quantity ?? ''}
                    onChange={(event) => action.edit('quantity', event.target.value)}
                  />
                </label>
                <label className="block">
                  New minimum fill
                  <input
                    className="block w-full rounded-lg border p-2"
                    inputMode="numeric"
                    value={state.values?.minQuantity ?? ''}
                    onChange={(event) => action.edit('minQuantity', event.target.value)}
                  />
                </label>
                <label className="block">
                  New price per share
                  <input
                    className="block w-full rounded-lg border p-2"
                    inputMode="decimal"
                    value={state.values?.pricePerShare ?? ''}
                    onChange={(event) => action.edit('pricePerShare', event.target.value)}
                  />
                </label>
              </>
            )}
            {state.error && <p role="alert">{state.error}</p>}
            <button className={button} onClick={() => void action.prepare()}>
              Review {label}
            </button>
          </>
        )}
        {replacements && (
          <div className="space-y-2">
            <p>New quantity: {replacements.quantity} shares</p>
            <p>New minimum fill: {replacements.minQuantity} shares</p>
            <p>New price per share: ${replacements.pricePerShare}</p>
          </div>
        )}
        {state.phase === 'ready' && (
          <>
            {!signing.walletReady && (
              <p>
                This exact wallet is unavailable for signing in the current account. The saved action remains available
                to check.
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
                  Sign {label}
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
              <QRScannerView scannerId="order-action-signature" error={scannerError} />
            )}
            {view.step !== 'instructions' && (
              <button
                className={button}
                onClick={() => {
                  stopScanner();
                  setSeedPhrase('');
                  signing.back();
                }}
              >
                Back
              </button>
            )}
          </>
        )}
        {state.phase === 'applied' && (
          <div role="status" className="space-y-2">
            <h3>{state.recovered ? 'Original action recovered' : 'Action recorded'}</h3>
            {state.snapshot?.result?.kind === 'cancel' && (
              <p>This cancellation changed the order from {state.snapshot.result.fromStatus} to cancelled.</p>
            )}
            {state.snapshot?.result?.kind === 'modify' && (
              <>
                <p>This change is modification {state.snapshot.result.modificationCount}.</p>
                {state.snapshot.result.changes.length === 0 && <p>The values were already the requested values.</p>}
                {state.snapshot.result.changes.map((change) => (
                  <p key={change.field}>
                    {change.field.replace(/_/g, ' ')}: {change.old} → {change.new}
                  </p>
                ))}
              </>
            )}
            <p>
              Current order status:{' '}
              {state.snapshot?.order.statusDisplay ?? state.snapshot?.order.status.replace(/_/g, ' ')}
            </p>
          </div>
        )}
        {state.phase === 'refused' && (
          <div role="status">
            <h3>{cancelling ? 'Cancellation declined' : 'Change declined'}</h3>
            <p>{state.snapshot?.refusal?.detail}</p>
            <p>This is the recorded result of the original request.</p>
          </div>
        )}
        {state.phase === 'error' && (
          <div role="alert" className="space-y-2">
            <h3>
              {state.canRemoveReminder
                ? 'Signing request rejected'
                : action.record
                  ? 'Action status unconfirmed'
                  : 'Order details unavailable'}
            </h3>
            <p>{state.error}</p>
            {action.record && !state.canRemoveReminder && (
              <p>
                Check the saved action before signing again. An unavailable result does not start a replacement action.
              </p>
            )}
            <button className={button} onClick={() => void action.recover()}>
              {action.record ? `Check ${label} status` : 'Retry order details'}
            </button>
            {state.canRemoveReminder && (
              <>
                <p>Removing this reminder does not cancel an action you already submitted.</p>
                <button className={button} onClick={() => void action.removeReminder()}>
                  Remove saved reminder
                </button>
              </>
            )}
          </div>
        )}
        {state.notice && <p>{state.notice}</p>}
        <button className="rounded-lg bg-surface-tertiary px-4 py-3" onClick={close}>
          {['applied', 'refused'].includes(state.phase) ? 'Done' : 'Close'}
        </button>
      </div>
    </Modal>
  );
}
