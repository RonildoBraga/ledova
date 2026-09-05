import { useState } from 'react';
import {
  CheckCircleIcon,
  ClockIcon,
  InfoIcon,
  ShieldCheckIcon,
  TrashIcon,
  UploadSimpleIcon,
  WarningIcon,
  XCircleIcon,
} from '@phosphor-icons/react';
import { useMutation } from '@tanstack/react-query';
import { Panel } from '@components/Panel';
import { deleteInvestorClassification, formatDate } from '@ledova/shared';
import type { InvestorCategory, InvestorClassification } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { CATEGORIES, REASON_TEXT, WHOLESALE_ONLY_NOTICE } from './constants';
import { ClaimModal } from './ClaimModal';
import { useInvestorEligibility } from './useInvestorEligibility';

function PageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full max-w-6xl mx-auto px-4 pt-6 pb-16 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 sm:gap-5 md:gap-6">{children}</div>
    </div>
  );
}

function StatusIcon({ classification }: { classification: InvestorClassification }) {
  if (classification.isLive) {
    return <CheckCircleIcon size={20} className="text-success-light flex-shrink-0" weight="fill" />;
  }
  if (classification.status === 'submitted') {
    return <ClockIcon size={20} className="text-info-light flex-shrink-0" weight="fill" />;
  }
  return <XCircleIcon size={20} className="text-error-light flex-shrink-0" weight="fill" />;
}

function claimState(classification: InvestorClassification) {
  if (classification.isLive) {
    return classification.expiresAt ? `Verified until ${formatDate(classification.expiresAt)}` : 'Verified';
  }
  if (classification.isExpired) return 'Expired';
  if (classification.status === 'submitted') return 'Awaiting review';
  return classification.statusDisplay;
}

export default function InvestorEligibilityPage() {
  const { eligibility, classifications, isLoading, refresh } = useInvestorEligibility();
  const [claimCategory, setClaimCategory] = useState<InvestorCategory | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (uuid: string) => deleteInvestorClassification(apiClient, uuid),
    onSuccess: refresh,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
      </div>
    );
  }

  const isEligible = eligibility?.isEligible ?? false;
  const openClaim = classifications.find((claim) => claim.status === 'submitted');
  const claimedCategories = new Set(
    classifications.filter((claim) => claim.isLive || claim.status === 'submitted').map((claim) => claim.category),
  );

  return (
    <PageWrapper>
      <Panel title="Wholesale Investor Status" icon={<ShieldCheckIcon size={20} />}>
        <div className="px-2 py-2 space-y-3">
          <div className="flex items-start gap-3">
            {isEligible ? (
              <CheckCircleIcon size={24} className="text-success-light flex-shrink-0" weight="fill" />
            ) : (
              <WarningIcon size={24} className="text-warning-light flex-shrink-0" weight="fill" />
            )}
            <div>
              <p className="text-sm font-medium text-text-primary">
                {isEligible ? 'You can see and subscribe to offerings' : 'You cannot subscribe to offerings yet'}
              </p>
              {!isEligible && (
                <ul className="mt-2 space-y-1">
                  {(eligibility?.reasons ?? []).map((reason) => (
                    <li key={reason} className="text-sm text-text-muted">
                      {REASON_TEXT[reason] ?? reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <p className="text-xs text-text-muted">{WHOLESALE_ONLY_NOTICE}</p>
        </div>
      </Panel>

      <Panel title="How You Qualify">
        <div className="divide-y divide-border-subtle">
          {CATEGORIES.map((item) => {
            const claimed = claimedCategories.has(item.category);
            return (
              <div key={item.category} className="px-2 py-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  {claimed ? (
                    <CheckCircleIcon size={20} className="text-success-light flex-shrink-0" weight="fill" />
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-border flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <span className="text-sm text-text-primary block">
                      {item.label} <span className="text-text-muted">({item.section})</span>
                    </span>
                    <span className="text-xs text-text-muted block">{item.evidence}</span>
                  </div>
                </div>
                <button
                  onClick={() => setClaimCategory(item.category)}
                  disabled={!!openClaim || !eligibility?.account}
                  className="text-brand-light hover:text-brand-subtle disabled:text-text-muted disabled:cursor-not-allowed p-1"
                  title={openClaim ? 'You already have a claim awaiting review' : 'Claim this category'}
                >
                  <UploadSimpleIcon size={16} />
                </button>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title="Your Claims">
        {classifications.length === 0 ? (
          <p className="px-2 py-4 text-sm text-text-muted">You have not made a claim yet.</p>
        ) : (
          <div className="divide-y divide-border-subtle">
            {classifications.map((claim) => (
              <div key={claim.uuid} className="px-2 py-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <StatusIcon classification={claim} />
                  <div className="min-w-0">
                    <span className="text-sm text-text-primary block truncate">{claim.categoryDisplay}</span>
                    <span className="text-xs text-text-muted block">
                      {claimState(claim)}
                      {claim.rejectionReason ? ` — ${claim.rejectionReason}` : ''}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {claim.status === 'submitted' && (
                    <button
                      onClick={() => deleteMutation.mutate(claim.uuid)}
                      disabled={deleteMutation.isPending}
                      className="text-error-light hover:text-error-light p-1"
                      title="Withdraw this claim"
                    >
                      <TrashIcon size={16} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="What Happens Next" icon={<InfoIcon size={20} />}>
        <div className="px-2 py-3">
          <ol className="list-decimal list-inside space-y-2 text-sm text-text-secondary">
            <li>Pick the category that applies to you and attach the evidence for it</li>
            <li>The operator reviews your evidence and sets an expiry date</li>
            <li>Once verified, offerings become visible and you can subscribe</li>
            <li>Re-evidence your claim before it expires to stay eligible</li>
          </ol>
        </div>
      </Panel>

      <ClaimModal
        isOpen={claimCategory !== null}
        onClose={() => setClaimCategory(null)}
        category={claimCategory}
        userAccount={eligibility?.account ?? null}
        onSuccess={() => {
          setClaimCategory(null);
          refresh();
        }}
      />
    </PageWrapper>
  );
}
