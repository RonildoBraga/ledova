import { useState } from 'react';
import { BankIcon, CheckIcon, CopyIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import { SUBSCRIPTION_COPY, formatDate } from '@ledova/shared';
import type { PaymentInstruction } from '@ledova/shared';

const COPIED_FOR_MS = 1500;

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    void navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), COPIED_FOR_MS);
    });
  };

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={`Copy ${label}`}
      className="ml-2 inline-flex items-center text-text-muted hover:text-text-primary transition-colors"
    >
      {copied ? <CheckIcon size={16} /> : <CopyIcon size={16} />}
    </button>
  );
}

function Row({ label, value, copyable = false }: { label: string; value: string; copyable?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 border-b border-border-subtle/40 last:border-b-0">
      <span className="text-sm text-text-muted">{label}</span>
      <span className="text-sm text-text-primary text-right flex items-baseline">
        <span className="font-mono break-all">{value}</span>
        {copyable && <CopyButton value={value} label={label} />}
      </span>
    </div>
  );
}

export function PaymentInstructionCard({ instruction }: { instruction: PaymentInstruction }) {
  const isBank = instruction.rail === 'bank_transfer';

  return (
    <Panel title="How To Pay" icon={<BankIcon size={20} />}>
      <div className="px-2 py-2 space-y-3">
        <p className="text-sm text-text-secondary">{SUBSCRIPTION_COPY.AWAITING_PAYMENT_HELP}</p>
        <div>
          <Row label="Reference" value={instruction.reference} copyable />
          <Row label="Amount" value={`${instruction.currency} ${instruction.amountDue}`} copyable />
          <Row label="Pay to" value={instruction.payee} />
          {isBank ? (
            <>
              <Row label="Account name" value={instruction.bankAccountName ?? '—'} copyable />
              <Row label="BSB" value={instruction.bankBsb ?? '—'} copyable />
              <Row label="Account number" value={instruction.bankAccountNumber ?? '—'} copyable />
            </>
          ) : (
            <>
              <Row label="Token" value={`${instruction.assetSymbol ?? '—'} on ${instruction.chain ?? '—'}`} />
              <Row label="Token contract" value={instruction.contractAddress ?? '—'} copyable />
              <Row label="Receiving wallet" value={instruction.receivingWalletAddress ?? '—'} copyable />
              <Row
                label={`Amount in raw units (${instruction.decimals ?? 0} decimals)`}
                value={instruction.settlementAmount ?? '—'}
                copyable
              />
            </>
          )}
          {instruction.paymentDueAt && <Row label="Due by" value={formatDate(instruction.paymentDueAt)} />}
        </div>
        {!isBank && (
          <p className="text-xs text-text-muted">
            Send the token itself, not the native coin, and send it on {instruction.chain ?? 'the stated chain'}. The
            operator confirms the transfer by its hash, and one transfer can fund one subscription only.
          </p>
        )}
      </div>
    </Panel>
  );
}
