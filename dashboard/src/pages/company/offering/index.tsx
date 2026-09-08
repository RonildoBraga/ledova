import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeftIcon, InfoIcon, MegaphoneIcon, UsersThreeIcon, XCircleIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import {
  OFFERING_EXEMPTION_LABELS,
  OFFERING_WITHDRAWABLE_STATUSES,
  REGISTER_COPY,
  formatDate,
  getErrorMessage,
  updateCompany,
} from '@ledova/shared';
import type { IssuerSubscription, Offering, OfferingExemption, OfferingInput } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { PageWrapper } from '../components/PageWrapper';
import { useCompany } from '../hooks/useCompany';
import { useOfferingActions, useOfferingUnderEdit, useOfferings, useOfferingSubscriptions } from './useOffering';
import { OfferingForm } from './OfferingForm';

const ACTION_ERROR_FALLBACK = 'The request was refused. Please try again.';

function OfferingRow({
  offering,
  onSubmit,
  onEdit,
  onWithdraw,
  onDelete,
  busy,
}: {
  offering: Offering;
  onSubmit: () => void;
  onEdit: () => void;
  onWithdraw: () => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const canWithdraw = OFFERING_WITHDRAWABLE_STATUSES.includes(offering.status);
  return (
    <div className="px-2 py-4 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-text-primary">
          {offering.tokenName} ({offering.tokenSymbol}) &mdash; {offering.statusDisplay}
        </p>
        <p className="text-xs text-text-muted mt-1">
          {offering.priceCurrency} {offering.pricePerShare} per share &middot; minimum {offering.minimumShares}, target{' '}
          {offering.targetShares}, cap {offering.capShares} shares
          {offering.maximumShares ? ` · at most ${offering.maximumShares} per investor` : ''}
        </p>
        <p className="text-xs text-text-muted">
          Opens {formatDate(offering.opensAt)}
          {offering.closesAt ? ` · closes ${formatDate(offering.closesAt)}` : ' · no closing date'}
        </p>
        <p className="text-xs text-text-muted">
          {OFFERING_EXEMPTION_LABELS[offering.exemption as OfferingExemption] ?? offering.exemptionDisplay}
        </p>
        {offering.status === 'rejected' && offering.rejectionReason && (
          <p className="text-xs text-error-light mt-1">Rejected: {offering.rejectionReason}</p>
        )}
        {offering.closeReason && <p className="text-xs text-text-muted mt-1">Closed: {offering.closeReason}</p>}
      </div>
      <div className="flex items-center gap-3">
        {offering.canBeEdited && (
          <button
            onClick={onSubmit}
            disabled={busy}
            className="rounded-lg bg-brand-mid hover:bg-brand disabled:bg-surface-disabled px-4 py-2 text-sm font-semibold text-white transition-colors"
          >
            {offering.status === 'rejected' ? 'Submit again' : 'Submit for review'}
          </button>
        )}
        {offering.canBeEdited && (
          <button
            onClick={onEdit}
            disabled={busy}
            className="text-sm font-medium text-text-muted hover:text-text-primary disabled:opacity-50 transition-colors"
          >
            Edit
          </button>
        )}
        {canWithdraw && (
          <button
            onClick={onWithdraw}
            disabled={busy}
            className="text-sm font-medium text-text-muted hover:text-error-light disabled:opacity-50 transition-colors"
          >
            Withdraw
          </button>
        )}
        {offering.canBeDeleted && (
          <button
            onClick={onDelete}
            disabled={busy}
            className="text-sm font-medium text-text-muted hover:text-error-light disabled:opacity-50 transition-colors"
          >
            Delete
          </button>
        )}
      </div>
    </div>
  );
}

function SubscriptionsPanel({ offerings }: { offerings: Offering[] }) {
  const [selected, setSelected] = useState<string>('');
  const uuid = selected || offerings[0]?.uuid;
  const { subscriptions, isLoading } = useOfferingSubscriptions(uuid);

  if (offerings.length === 0) {
    return null;
  }

  return (
    <Panel title={REGISTER_COPY.SUBSCRIPTIONS_TITLE} icon={<UsersThreeIcon size={20} />}>
      <div className="px-2 py-2 space-y-3">
        <p className="text-sm text-text-secondary">{REGISTER_COPY.SUBSCRIPTIONS_NOTE}</p>
        <select
          value={uuid}
          onChange={(event) => setSelected(event.target.value)}
          className="rounded-lg border border-border bg-surface-secondary px-3 py-2 text-sm text-text-primary"
        >
          {offerings.map((offering) => (
            <option key={offering.uuid} value={offering.uuid}>
              {offering.tokenSymbol} &mdash; {offering.statusDisplay}
            </option>
          ))}
        </select>
        {isLoading ? (
          <div className="py-4 text-center">
            <div className="h-5 w-5 border-2 border-brand-subtle border-t-brand rounded-full animate-spin mx-auto" />
          </div>
        ) : subscriptions.length === 0 ? (
          <p className="text-sm text-text-muted">{REGISTER_COPY.SUBSCRIPTIONS_EMPTY}</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-3 py-2 text-left text-xs font-medium text-text-muted">Investor</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-text-muted">Shares</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-text-muted">Due</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-text-muted">Received</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-text-muted">Status</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-text-muted">Allotment</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {subscriptions.map((row: IssuerSubscription) => (
                  <tr key={row.uuid}>
                    <td className="px-3 py-2 text-text-primary">{row.investorName || row.walletAddress}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-text-primary">
                      {(row.allottedQuantity ?? row.quantity).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-text-muted">{row.amountDue}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-text-muted">{row.amountReceived ?? '—'}</td>
                    <td className="px-3 py-2 text-text-secondary">{row.statusDisplay}</td>
                    <td className="px-3 py-2 text-text-secondary">{row.allotmentState}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Panel>
  );
}

export default function OfferingPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { company, companyUuid, isLoading: isLoadingCompany } = useCompany();
  const { offerings, tokens, settlementAssets, isLoading: isLoadingOfferings, refresh } = useOfferings();
  const [actionError, setActionError] = useState<string | null>(null);
  const [editingUuid, setEditingUuid] = useState<string | null>(null);
  const { offering: editing, isLoading: isLoadingEditing } = useOfferingUnderEdit(editingUuid ?? undefined);

  const settle = () => {
    setActionError(null);
    setEditingUuid(null);
    refresh();
  };
  const surfaceError = (error: unknown) => setActionError(getErrorMessage(error, ACTION_ERROR_FALLBACK));
  const actions = useOfferingActions(settle);

  const listingMutation = useMutation({
    mutationFn: (isOpen: boolean) => updateCompany(apiClient, companyUuid!, { isOpenToInvestors: isOpen }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['company', companyUuid] }),
    onError: surfaceError,
  });

  const run = (promise: Promise<unknown>) => promise.catch(surfaceError);

  if (isLoadingCompany || isLoadingOfferings) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  if (!company) {
    return (
      <div className="text-center py-20">
        <p className="text-text-muted">No company found. Please register your company first.</p>
      </div>
    );
  }

  const busy =
    actions.create.isPending ||
    actions.update.isPending ||
    actions.submit.isPending ||
    actions.withdraw.isPending ||
    actions.remove.isPending ||
    listingMutation.isPending;

  const handleCreate = (input: OfferingInput) => run(actions.create.mutateAsync(input));
  const handleUpdate = (input: OfferingInput) => run(actions.update.mutateAsync({ uuid: editingUuid!, data: input }));
  const startEditing = (uuid: string) => {
    setActionError(null);
    setEditingUuid(uuid);
  };

  return (
    <PageWrapper>
      {actionError && (
        <div className="flex items-start gap-3 p-4 rounded-lg bg-error-light/10 border border-error-light/30">
          <XCircleIcon size={20} className="text-error-light flex-shrink-0 mt-0.5" weight="fill" />
          <p className="text-sm text-error-light">{actionError}</p>
        </div>
      )}

      <Panel title="Investor Directory" icon={<MegaphoneIcon size={20} />}>
        <div className="px-2 py-2 space-y-3">
          <p className="text-sm text-text-secondary">
            Your company is listed in the investor directory only while this is on. Nothing is listed by default, and
            the operator can switch it off. Turning it off hides your share classes; it does not withdraw an offering
            already under review.
          </p>
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={company.isOpenToInvestors}
              disabled={!company.canIssueTokens || busy}
              onChange={(event) => listingMutation.mutate(event.target.checked)}
              className="h-4 w-4 rounded border-border"
            />
            <span className="text-sm text-text-primary">Show this company to eligible investors</span>
          </label>
          {!company.canIssueTokens && (
            <p className="text-xs text-warning-light">
              Your company must be active before it can be listed. It is currently {company.statusDisplay}.
            </p>
          )}
        </div>
      </Panel>

      <Panel title="Your Offerings">
        {offerings.length === 0 ? (
          <div className="px-2 py-6 text-sm text-text-muted">
            You have no offerings yet. Create one below and submit it for review.
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {offerings.map((offering) => (
              <OfferingRow
                key={offering.uuid}
                offering={offering}
                busy={busy}
                onSubmit={() => run(actions.submit.mutateAsync(offering.uuid))}
                onEdit={() => startEditing(offering.uuid)}
                onWithdraw={() =>
                  run(actions.withdraw.mutateAsync({ uuid: offering.uuid, reason: 'Withdrawn by the issuer' }))
                }
                onDelete={() => run(actions.remove.mutateAsync(offering.uuid))}
              />
            ))}
          </div>
        )}
      </Panel>

      <SubscriptionsPanel offerings={offerings} />

      {editingUuid && isLoadingEditing ? (
        <Panel title="Edit offering">
          <div className="px-2 py-6 text-sm text-text-muted">Loading the offering&rsquo;s current values&hellip;</div>
        </Panel>
      ) : (
        <OfferingForm
          key={editing?.uuid ?? 'new'}
          tokens={tokens}
          busy={busy}
          settlementAssets={settlementAssets}
          onCreate={handleCreate}
          editing={editing}
          onUpdate={handleUpdate}
          onCancelEdit={() => setEditingUuid(null)}
        />
      )}

      <Panel title="What Happens Next" icon={<InfoIcon size={20} />}>
        <div className="px-2 py-2">
          <ol className="list-decimal list-inside space-y-2 text-sm text-text-secondary">
            <li>Submit the offering; the operator reviews the bounds, the window and the exemption relied on</li>
            <li>Once approved, it opens automatically at the opening time you set</li>
            <li>Eligible investors see it in the directory and can subscribe</li>
            <li>The operator closes it deliberately; reaching the cap does not close it on its own</li>
          </ol>
        </div>
      </Panel>

      <div>
        <button
          onClick={() => navigate('/company')}
          className="flex items-center gap-2 text-sm text-text-muted hover:text-text-primary transition-colors"
        >
          <ArrowLeftIcon size={16} />
          Back to Company
        </button>
      </div>
    </PageWrapper>
  );
}
