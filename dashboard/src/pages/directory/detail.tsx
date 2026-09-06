import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeftIcon, BankIcon, CoinsIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import { formatDate } from '@ledova/shared';
import type { Operator } from '@ledova/shared';
import { useSelectedPortfolio } from '@hooks';
import { SubscribeForm } from '@pages/subscriptions/SubscribeForm';
import { useCreateSubscription, useSubscribableWallets } from '@pages/subscriptions/useSubscriptions';
import { useDirectoryToken } from './useDirectory';

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

function PaymentPanel({ operator }: { operator: Operator | null }) {
  const instructions = operator?.paymentInstructions;
  if (!instructions) return null;
  const hasBank = Boolean(instructions.bankAccountName && instructions.bankBsb && instructions.bankAccountNumber);
  const hasWallet = Boolean(instructions.receivingWalletAddress);

  return (
    <Panel title="How Settlement Works" icon={<BankIcon size={20} />}>
      <div className="px-2 py-2 space-y-3">
        <p className="text-sm text-text-secondary">
          Money for a subscription is paid to {operator?.name}, not to the company. Your exact reference and amount are
          issued when a subscription is accepted; these are the rails available today.
        </p>
        <div>
          {hasBank && (
            <>
              <Row label="Bank account name" value={instructions.bankAccountName} />
              <Row label="BSB" value={instructions.bankBsb} />
              <Row label="Account number" value={instructions.bankAccountNumber} />
            </>
          )}
          {hasWallet && (
            <Row
              label={`Receiving wallet (${instructions.receivingWalletChain})`}
              value={<span className="font-mono break-all">{instructions.receivingWalletAddress}</span>}
            />
          )}
          {(operator?.supportedSettlementAssets ?? []).length > 0 && (
            <Row
              label="Settlement stablecoins"
              value={(operator?.supportedSettlementAssets ?? []).map((asset) => asset.symbol).join(', ')}
            />
          )}
        </div>
        {!hasBank && !hasWallet && (
          <p className="text-sm text-text-muted">
            {operator?.name ?? 'The operator'} has not published payment details yet.
          </p>
        )}
      </div>
    </Panel>
  );
}

export default function DirectoryTokenPage() {
  const { uuid } = useParams<{ uuid: string }>();
  const navigate = useNavigate();
  const { token, operator, isLoading, notFound } = useDirectoryToken(uuid);
  const { selectedAccount } = useSelectedPortfolio();
  const { wallets } = useSubscribableWallets();
  const create = useCreateSubscription((created) => navigate(`/subscriptions/${created}`));

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  if (!token || notFound) {
    return (
      <PageWrapper>
        <Panel title="Not Available">
          <div className="px-2 py-8 text-center">
            <p className="text-text-muted">
              This share class is not in the directory. It may not be open to investors, or your investor status may not
              be verified.
            </p>
            <Link to="/directory" className="mt-4 inline-block text-brand-light hover:text-brand-subtle font-medium">
              Back to the directory
            </Link>
          </div>
        </Panel>
      </PageWrapper>
    );
  }

  const offering = token.openOffering;

  return (
    <PageWrapper>
      <Panel title={`${token.company.displayName} (${token.symbol})`} icon={<CoinsIcon size={20} />}>
        <div className="px-2 py-2">
          <Row label="Share class" value={token.name} />
          <Row label="Industry" value={token.company.industry || '—'} />
          <Row label="Location" value={[token.company.city, token.company.state].filter(Boolean).join(', ') || '—'} />
          <Row label="Authorized shares" value={Number(token.totalSupply).toLocaleString()} />
          <Row label="Shares issued" value={token.issuedShares.toLocaleString()} />
          <Row label="Last traded price" value={token.lastPrice ?? '—'} />
        </div>
      </Panel>

      <Panel title="Current Offering">
        <div className="px-2 py-2">
          {offering ? (
            <>
              <Row label="Price per share" value={`${offering.priceCurrency} ${offering.pricePerShare}`} />
              <Row label="Opened" value={formatDate(offering.opensAt)} />
              <Row label="Closes" value={offering.closesAt ? formatDate(offering.closesAt) : 'No closing date'} />
            </>
          ) : (
            <p className="py-4 text-sm text-text-muted">
              This company has no offering open. An offering appears here only once the operator has approved it and its
              opening time has passed; until then there is nothing to subscribe to.
            </p>
          )}
        </div>
      </Panel>

      {offering && (
        <SubscribeForm
          offering={offering}
          wallets={wallets}
          accountUuid={selectedAccount?.uuid ?? null}
          busy={create.isPending}
          error={create.error}
          onSubscribe={({ wallet, quantity }) =>
            create.mutate({ offering: offering.uuid, userAccount: selectedAccount!.uuid, wallet, quantity })
          }
        />
      )}

      <PaymentPanel operator={operator} />

      <div>
        <Link
          to="/directory"
          className="flex items-center gap-2 text-sm text-text-muted hover:text-text-primary transition-colors"
        >
          <ArrowLeftIcon size={16} />
          Back to the directory
        </Link>
      </div>
    </PageWrapper>
  );
}
