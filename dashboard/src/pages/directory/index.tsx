import { Link } from 'react-router-dom';
import { BuildingsIcon, ShieldCheckIcon, StorefrontIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import { DIRECTORY_COPY, formatDate } from '@ledova/shared';
import type { DirectoryToken } from '@ledova/shared';
import { useDirectoryTokens } from './useDirectory';

function PageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">{children}</div>
    </div>
  );
}

function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="px-4 py-12 text-center">
      <BuildingsIcon size={48} className="text-text-muted mx-auto mb-4" weight="duotone" />
      <h3 className="text-lg font-semibold text-text-primary mb-2">{title}</h3>
      <p className="text-text-muted max-w-xl mx-auto">{body}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

function TokenRow({ token }: { token: DirectoryToken }) {
  const offering = token.openOffering;
  return (
    <Link
      to={`/directory/${token.uuid}`}
      className="block px-4 py-4 hover:bg-surface-tertiary/50 transition-colors border-b border-border-subtle/40 last:border-b-0"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text-primary">
            {token.company.displayName} <span className="text-text-muted">({token.symbol})</span>
          </p>
          <p className="text-xs text-text-muted mt-0.5">
            {[token.company.industry, token.company.city, token.company.state].filter(Boolean).join(' · ') ||
              'Location not stated'}
          </p>
          <p className="text-xs text-text-muted mt-0.5">{token.issuedShares.toLocaleString()} shares issued</p>
        </div>
        <div className="text-right">
          {offering ? (
            <>
              <p className="text-sm font-mono text-text-primary">
                {offering.priceCurrency} {offering.pricePerShare}
              </p>
              <p className="text-xs text-text-muted">
                Open since {formatDate(offering.opensAt)}
                {offering.closesAt ? ` · closes ${formatDate(offering.closesAt)}` : ''}
              </p>
            </>
          ) : (
            <p className="text-xs text-text-muted">No offering open</p>
          )}
        </div>
      </div>
    </Link>
  );
}

export default function DirectoryPage() {
  const { tokens, isEligible, isLoading } = useDirectoryTokens();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <PageWrapper>
      <Panel title="Investor Directory" icon={<StorefrontIcon size={20} />}>
        {!isEligible ? (
          <EmptyState
            title={DIRECTORY_COPY.INELIGIBLE_TITLE}
            body={DIRECTORY_COPY.INELIGIBLE_BODY}
            action={
              <Link
                to="/investor-eligibility"
                className="inline-flex items-center gap-2 rounded-lg bg-brand-mid hover:bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors"
              >
                <ShieldCheckIcon size={16} />
                Verify my investor status
              </Link>
            }
          />
        ) : tokens.length === 0 ? (
          <EmptyState title={DIRECTORY_COPY.EMPTY_TITLE} body={DIRECTORY_COPY.EMPTY_BODY} />
        ) : (
          <div className="-mx-4">
            {tokens.map((token) => (
              <TokenRow key={token.uuid} token={token} />
            ))}
          </div>
        )}
      </Panel>
    </PageWrapper>
  );
}
