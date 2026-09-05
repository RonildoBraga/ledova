import { useState } from 'react';
import { formatWalletAddressMedium, normalizeBitcoinRawTransactionHex } from '@ledova/shared-utils';
import type { PrepareBitcoinTransferResponse } from '@ledova/shared-types';

interface BitcoinSignStepProps {
  prepared: PrepareBitcoinTransferResponse;
  signedTransaction: string;
  onSignedTransactionChange: (value: string) => void;
  onCancel: () => void;
  onBroadcast: (signedTransactionHex: string) => void;
}

const INSTRUCTIONS = [
  'In your own Bitcoin wallet software, build a transaction from this address that pays the amount below to the recipient at the fee rate shown.',
  'Sign it there and export the signed raw transaction as hex.',
  'Paste the signed hex below and broadcast it to the network.',
];

export const INVALID_SIGNED_HEX_MESSAGE =
  'Enter the signed raw transaction as hex (whole bytes; an optional 0x prefix is removed).';

export function BitcoinSignStep({
  prepared,
  signedTransaction,
  onSignedTransactionChange,
  onCancel,
  onBroadcast,
}: BitcoinSignStepProps) {
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleBroadcast = () => {
    const normalized = normalizeBitcoinRawTransactionHex(signedTransaction);
    if (!normalized) {
      setValidationError(INVALID_SIGNED_HEX_MESSAGE);
      return;
    }
    setValidationError(null);
    onBroadcast(normalized);
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-text-muted">
        This app does not build or sign Bitcoin transactions. Sign with your own wallet software and paste the result.
      </p>

      <div className="bg-surface-tertiary rounded-lg p-4">
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-text-muted">From</dt>
          <dd className="text-text-primary font-mono text-xs">{formatWalletAddressMedium(prepared.fromAddress)}</dd>
          <dt className="text-text-muted">To</dt>
          <dd className="text-text-primary font-mono text-xs break-all">{prepared.toAddress}</dd>
          <dt className="text-text-muted">Amount</dt>
          <dd className="text-text-primary font-medium">{prepared.amountBtc} BTC</dd>
          <dt className="text-text-muted">Fee rate</dt>
          <dd className="text-text-primary">{prepared.feePerByte} sat/vB</dd>
          <dt className="text-text-muted">Estimated size</dt>
          <dd className="text-text-primary">{prepared.estimatedTxSize} vB</dd>
          <dt className="text-text-muted">Fee</dt>
          <dd className="text-text-primary">{prepared.feeBtc} BTC</dd>
          <dt className="text-text-muted">Total</dt>
          <dd className="text-text-primary font-medium">{prepared.totalCostBtc} BTC</dd>
        </dl>
      </div>

      <ol className="space-y-3">
        {INSTRUCTIONS.map((instruction, index) => (
          <li key={instruction} className="flex items-start gap-3 p-3 bg-surface-tertiary rounded-lg">
            <span className="flex-shrink-0 w-6 h-6 bg-brand-mid text-white text-sm font-semibold rounded-full flex items-center justify-center">
              {index + 1}
            </span>
            <p className="text-sm text-text-secondary">{instruction}</p>
          </li>
        ))}
      </ol>

      <div className="space-y-2">
        <label htmlFor="bitcoin-signed-transaction" className="text-sm font-medium text-text-primary">
          Signed transaction (hex)
        </label>
        <textarea
          id="bitcoin-signed-transaction"
          value={signedTransaction}
          onChange={(event) => onSignedTransactionChange(event.target.value)}
          placeholder="02000000..."
          rows={4}
          spellCheck={false}
          className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-3 text-xs text-text-primary font-mono placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid resize-none"
        />
        {validationError && <p className="text-xs text-error-light">{validationError}</p>}
      </div>

      <div className="flex gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 py-3 rounded-lg font-medium text-text-primary bg-surface-tertiary hover:bg-surface-disabled transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleBroadcast}
          disabled={signedTransaction.trim().length === 0}
          className="flex-1 py-3 rounded-lg font-medium text-white bg-brand-mid hover:bg-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Broadcast
        </button>
      </div>
    </div>
  );
}
