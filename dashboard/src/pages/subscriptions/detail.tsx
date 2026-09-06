import { Link, useParams } from 'react-router-dom';
import { ArrowLeftIcon, HandCoinsIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import {
  SUBSCRIPTION_COPY,
  SUBSCRIPTION_SUBMITTABLE_STATUSES,
  SUBSCRIPTION_WITHDRAWABLE_STATUSES,
  formatDate,
  getErrorMessage,
} from '@ledova/shared';
import type { SubscriptionDetail } from '@ledova/shared';
import { PaymentInstructionCard } from './PaymentInstructionCard';
import { useSubscription } from './useSubscriptions';

const ACTION_ERROR_FALLBACK = 'The request was refused. Please try again.';

const STATUS_HELP: Record<string, string> = {
  draft: SUBSCRIPTION_COPY.DRAFT_HELP,
  submitted: 'The operator is reviewing your subscription. Nothing is payable until it is accepted.',
  accepted: 'Accepted. The payment instruction is being issued.',
  awaiting_payment: SUBSCRIPTION_COPY.AWAITING_PAYMENT_HELP,
  paid: SUBSCRIPTION_COPY.PAID_HELP,
  allotted: SUBSCRIPTION_COPY.ALLOTTED_HELP,
  refunded: 'The operator has recorded a refund against this subscription. Nothing has been allotted.',
};

function PageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-4xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2 border-b border-border-subtle/40 last:border-b-0">
      <span className="text-sm text-text-muted">{label}</span>
      <span className="text-sm text-text-primary text-right">{value}</span>
    </div>
  );
}

function Summary({ subscription }: { subscription: SubscriptionDetail }) {
  return (
    <Panel title={`${subscription.companyName} (${subscription.tokenSymbol})`} icon={<HandCoinsIcon size={20} />}>
      <div className="px-2 py-2">
        <Row label="Status" value={subscription.statusDisplay} />
        <Row label="Shares requested" value={subscription.quantity.toLocaleString()} />
        {subscription.allottedQuantity !== null && subscription.allottedQuantity !== subscription.quantity && (
          <Row label="Shares to be allotted" value={subscription.allottedQuantity.toLocaleString()} />
        )}
        <Row label="Price per share" value={subscription.pricePerShare} />
        <Row label="Amount due" value={subscription.amountDue} />
        {subscription.amountReceived && <Row label="Amount received" value={subscription.amountReceived} />}
        {subscription.refundAmount && <Row label="Refund" value={subscription.refundAmount} />}
        <Row
          label="Receiving wallet"
          value={<span className="font-mono break-all">{subscription.walletAddress}</span>}
        />
        <Row label="Created" value={formatDate(subscription.createdAt)} />
      </div>
    </Panel>
  );
}

export default function SubscriptionDetailPage() {
  const { uuid } = useParams<{ uuid: string }>();
  const { subscription, isLoading, notFound, submit, withdraw } = useSubscription(uuid);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  if (!subscription || notFound) {
    return (
      <PageWrapper>
        <Panel title="Not Available">
          <div className="px-2 py-8 text-center">
            <p className="text-text-muted">This subscription is not one of yours, or it no longer exists.</p>
            <Link
              to="/subscriptions"
              className="mt-4 inline-block text-brand-light hover:text-brand-subtle font-medium"
            >
              Back to my subscriptions
            </Link>
          </div>
        </Panel>
      </PageWrapper>
    );
  }

  const canSubmit = SUBSCRIPTION_SUBMITTABLE_STATUSES.includes(subscription.status);
  const canWithdraw = SUBSCRIPTION_WITHDRAWABLE_STATUSES.includes(subscription.status) && !subscription.amountReceived;
  const busy = submit.isPending || withdraw.isPending;
  const message = getErrorMessage(submit.error ?? withdraw.error, ACTION_ERROR_FALLBACK);
  const help = STATUS_HELP[subscription.status];

  return (
    <PageWrapper>
      {message && <p className="text-sm text-error-light">{message}</p>}

      <Summary subscription={subscription} />

      {subscription.paymentInstruction && <PaymentInstructionCard instruction={subscription.paymentInstruction} />}

      {help && (
        <Panel title="What Happens Next">
          <div className="px-2 py-2 space-y-2">
            <p className="text-sm text-text-secondary">{help}</p>
            {subscription.amountReceived && !canWithdraw && (
              <p className="text-xs text-text-muted">{SUBSCRIPTION_COPY.MONEY_IN_HELP}</p>
            )}
          </div>
        </Panel>
      )}

      {(canSubmit || canWithdraw) && (
        <div className="flex flex-wrap gap-3">
          {canSubmit && (
            <button
              type="button"
              disabled={busy}
              onClick={() => submit.mutate()}
              className="rounded-lg bg-brand-mid hover:bg-brand disabled:opacity-50 px-5 py-2.5 text-sm font-semibold text-white transition-colors"
            >
              Submit for review
            </button>
          )}
          {canWithdraw && (
            <button
              type="button"
              disabled={busy}
              onClick={() => withdraw.mutate('Withdrawn by the investor')}
              className="rounded-lg border border-border px-5 py-2.5 text-sm font-semibold text-text-primary hover:bg-surface-tertiary/50 transition-colors"
            >
              Withdraw
            </button>
          )}
        </div>
      )}

      <div>
        <Link
          to="/subscriptions"
          className="flex items-center gap-2 text-sm text-text-muted hover:text-text-primary transition-colors"
        >
          <ArrowLeftIcon size={16} />
          Back to my subscriptions
        </Link>
      </div>
    </PageWrapper>
  );
}
