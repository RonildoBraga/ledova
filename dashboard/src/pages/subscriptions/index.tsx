import { Link } from 'react-router-dom';
import { HandCoinsIcon, StorefrontIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import { SUBSCRIPTION_COPY, formatDate } from '@ledova/shared';
import type { Subscription } from '@ledova/shared';
import { useSubscriptions } from './useSubscriptions';

function PageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-4xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">{children}</div>
    </div>
  );
}

function SubscriptionRow({ subscription }: { subscription: Subscription }) {
  return (
    <Link
      to={`/subscriptions/${subscription.uuid}`}
      className="block px-4 py-4 hover:bg-surface-tertiary/50 transition-colors border-b border-border-subtle/40 last:border-b-0"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text-primary">
            {subscription.companyName} <span className="text-text-muted">({subscription.tokenSymbol})</span>
          </p>
          <p className="text-xs text-text-muted mt-0.5">
            {subscription.quantity.toLocaleString()} shares at {subscription.pricePerShare} ·{' '}
            {formatDate(subscription.createdAt)}
          </p>
          {subscription.reference && (
            <p className="text-xs text-text-muted mt-0.5 font-mono">Reference {subscription.reference}</p>
          )}
        </div>
        <div className="text-right">
          <p className="text-sm font-mono text-text-primary">{subscription.amountDue}</p>
          <p className="text-xs text-text-muted">{subscription.statusDisplay}</p>
        </div>
      </div>
    </Link>
  );
}

export default function SubscriptionsPage() {
  const { subscriptions, isLoading } = useSubscriptions();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <PageWrapper>
      <Panel title={SUBSCRIPTION_COPY.LIST_TITLE} icon={<HandCoinsIcon size={20} />}>
        {subscriptions.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <StorefrontIcon size={48} className="text-text-muted mx-auto mb-4" weight="duotone" />
            <h3 className="text-lg font-semibold text-text-primary mb-2">{SUBSCRIPTION_COPY.EMPTY_TITLE}</h3>
            <p className="text-text-muted max-w-xl mx-auto">{SUBSCRIPTION_COPY.EMPTY_BODY}</p>
            <Link
              to="/directory"
              className="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-mid hover:bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors"
            >
              Browse the directory
            </Link>
          </div>
        ) : (
          <div className="-mx-4">
            {subscriptions.map((subscription) => (
              <SubscriptionRow key={subscription.uuid} subscription={subscription} />
            ))}
          </div>
        )}
      </Panel>
    </PageWrapper>
  );
}
