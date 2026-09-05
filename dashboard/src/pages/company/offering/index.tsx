import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeftIcon, InfoIcon, MegaphoneIcon, XCircleIcon } from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import {
  OFFERING_EXEMPTION_LABELS,
  OFFERING_WITHDRAWABLE_STATUSES,
  formatDate,
  getErrorMessage,
  updateCompany,
} from '@ledova/shared';
import type { Offering, OfferingExemption, OfferingInput } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { PageWrapper } from '../components/PageWrapper';
import { useCompany } from '../hooks/useCompany';
import { useOfferingActions, useOfferings } from './useOffering';
import { OfferingForm } from './OfferingForm';

const ACTION_ERROR_FALLBACK = 'The request was refused. Please try again.';

function OfferingRow({
  offering,
  onSubmit,
  onWithdraw,
  onDelete,
  busy,
}: {
  offering: Offering;
  onSubmit: () => void;
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
        {offering.rejectionReason && (
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
            Submit for review
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
        {offering.canBeEdited && (
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

export default function OfferingPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { company, companyUuid, isLoading: isLoadingCompany } = useCompany();
  const { offerings, tokens, isLoading: isLoadingOfferings, refresh } = useOfferings();
  const [actionError, setActionError] = useState<string | null>(null);

  const settle = () => {
    setActionError(null);
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
    actions.submit.isPending ||
    actions.withdraw.isPending ||
    actions.remove.isPending ||
    listingMutation.isPending;

  const handleCreate = (input: OfferingInput) => run(actions.create.mutateAsync(input));

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
                onWithdraw={() =>
                  run(actions.withdraw.mutateAsync({ uuid: offering.uuid, reason: 'Withdrawn by the issuer' }))
                }
                onDelete={() => run(actions.remove.mutateAsync(offering.uuid))}
              />
            ))}
          </div>
        )}
      </Panel>

      <OfferingForm tokens={tokens} busy={busy} onCreate={handleCreate} />

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
