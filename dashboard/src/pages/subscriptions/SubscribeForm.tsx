import { useState } from 'react';
import { Link } from 'react-router-dom';
import { HandCoinsIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import { SUBSCRIPTION_COPY, getErrorMessage } from '@ledova/shared';
import type { DirectoryOpenOffering, Wallet } from '@ledova/shared';

const FIELD_CLASS =
  'mt-1 w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary ' +
  'placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid';

const CREATE_ERROR_FALLBACK = 'The subscription was refused. Please check the quantity and try again.';

interface SubscribeFormProps {
  offering: DirectoryOpenOffering;
  wallets: Wallet[];
  accountUuid: string | null;
  busy: boolean;
  error: unknown;
  onSubscribe: (input: { wallet: string; quantity: number }) => void;
}

function amountFor(quantity: string, price: string) {
  const shares = Number(quantity);
  if (!Number.isFinite(shares) || shares <= 0) return null;
  return (shares * Number(price)).toFixed(2);
}

export function SubscribeForm({ offering, wallets, accountUuid, busy, error, onSubscribe }: SubscribeFormProps) {
  const [quantity, setQuantity] = useState('');
  const [wallet, setWallet] = useState('');

  const chosenWallet = wallet || wallets[0]?.uuid || '';
  const amount = amountFor(quantity, offering.pricePerShare);
  const message = getErrorMessage(error, CREATE_ERROR_FALLBACK);

  if (wallets.length === 0) {
    return (
      <Panel title={SUBSCRIPTION_COPY.NO_WALLET_TITLE} icon={<HandCoinsIcon size={20} />}>
        <div className="px-2 py-4 space-y-3">
          <p className="text-sm text-text-secondary">{SUBSCRIPTION_COPY.NO_WALLET_BODY}</p>
          <Link
            to="/wallets"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-mid hover:bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors"
          >
            Go to my wallets
          </Link>
        </div>
      </Panel>
    );
  }

  return (
    <Panel title={SUBSCRIPTION_COPY.SUBSCRIBE_TITLE} icon={<HandCoinsIcon size={20} />}>
      <div className="px-2 py-2 space-y-4">
        <p className="text-sm text-text-secondary">{SUBSCRIPTION_COPY.SUBSCRIBE_INTRO}</p>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-text-primary">Shares</span>
            <input
              type="number"
              min={1}
              step={1}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              className={FIELD_CLASS}
              placeholder="Whole shares"
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-text-primary">Receiving wallet (Base)</span>
            <select value={chosenWallet} onChange={(event) => setWallet(event.target.value)} className={FIELD_CLASS}>
              {wallets.map((item) => (
                <option key={item.uuid} value={item.uuid}>
                  {item.name ? `${item.name} — ` : ''}
                  {item.address}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex items-baseline justify-between gap-4 py-2 border-t border-border-subtle/40">
          <span className="text-sm text-text-muted">Amount payable on acceptance</span>
          <span className="text-sm font-mono text-text-primary">
            {amount ? `${offering.priceCurrency} ${amount}` : '—'}
          </span>
        </div>

        {message && <p className="text-sm text-error-light">{message}</p>}

        <button
          type="button"
          disabled={busy || !amount || !chosenWallet || !accountUuid}
          onClick={() => onSubscribe({ wallet: chosenWallet, quantity: Number(quantity) })}
          className="rounded-lg bg-brand-mid hover:bg-brand disabled:opacity-50 px-5 py-2.5 text-sm font-semibold text-white transition-colors"
        >
          Create subscription
        </button>

        <p className="text-xs text-text-muted">{SUBSCRIPTION_COPY.DRAFT_HELP}</p>
      </div>
    </Panel>
  );
}
