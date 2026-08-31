import { PageWrapper } from '../components/PageWrapper';
import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useSetPageTitle } from '@hooks/usePageTitle';
import { Panel } from '@components/Panel';
import { Modal } from '@components/Modal';
import { Field, Label, Input } from '@headlessui/react';
import {
  CopyIcon,
  CheckCircleIcon,
  ClockIcon,
  WarningIcon,
  UsersThreeIcon,
  ListBulletsIcon,
  CoinIcon,
  InfoIcon,
  TrendUpIcon,
} from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared-constants';
import { useTokenDetail } from '../hooks/useTokens';
import { issueCompanyShares } from '@ledova/shared-services';
import apiClient from '@services/apiClient';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import type {
  TokenTabType,
  TokenType,
  TokenStatus,
  TokenHolder,
  TokenIssuance,
  CapitalIncreaseRequest,
  CapitalIncreaseStatus,
} from '@ledova/shared-types';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

type RightTab = 'holders' | 'issuances';

const TOKEN_TYPE_LABELS: Record<TokenType, string> = {
  ordinary: 'Ordinary',
  preference: 'Preference',
  redeemable: 'Redeemable',
};

const STATUS_LABELS: Record<TokenStatus, string> = {
  draft: 'Draft',
  deploying: 'Deploying',
  deployed: 'Deployed',
  paused: 'Paused',
};

const STATUS_COLORS: Record<TokenStatus, string> = {
  draft: 'bg-surface-tertiary text-text-muted',
  deploying: 'bg-info-light/20 text-info-light',
  deployed: 'bg-success-light/20 text-success-light',
  paused: 'bg-error-light/20 text-error-light',
};

const CAPITAL_INCREASE_STATUS_COLORS: Record<CapitalIncreaseStatus, string> = {
  draft: 'bg-surface-tertiary text-text-muted',
  submitted: 'bg-info-light/20 text-info-light',
  under_review: 'bg-info-light/20 text-info-light',
  approved: 'bg-success-light/20 text-success-light',
  rejected: 'bg-error-light/20 text-error-light',
  executing: 'bg-info-light/20 text-info-light',
  executed: 'bg-success-light/20 text-success-light',
  failed: 'bg-error-light/20 text-error-light',
};

const CAPITAL_INCREASE_STATUS_LABELS: Record<CapitalIncreaseStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  under_review: 'Under Review',
  approved: 'Approved',
  rejected: 'Rejected',
  executing: 'Executing',
  executed: 'Executed',
  failed: 'Failed',
};

// Map right tab to hook's tab type for data fetching
const RIGHT_TAB_TO_HOOK: Record<RightTab, TokenTabType> = {
  holders: 'shareholders',
  issuances: 'issuances',
};

function CopiedIcon({ copied }: { copied: boolean }) {
  return copied ? <CheckCircleIcon size={14} className="text-success-light" /> : <CopyIcon size={14} />;
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="h-6 w-6 border-3 border-brand-subtle border-t-brand rounded-full animate-spin" />
    </div>
  );
}

export default function TokenDetailPage() {
  const { uuid } = useParams<{ uuid: string }>();
  const queryClient = useQueryClient();

  const {
    token,
    isLoading,
    error,
    setActiveTab,
    holders,
    totalHolders,
    isLoadingHolders,
    issuances,
    issuanceCount,
    isLoadingIssuances,
    capitalIncreases,
    isLoadingCapitalIncreases,
  } = useTokenDetail(uuid!);

  const setPageTitle = useSetPageTitle();

  useEffect(() => {
    if (token) setPageTitle(token.name);
    return () => setPageTitle('Company', 'Manage your company');
  }, [token, setPageTitle]);

  const [rightTab, setRightTab] = useState<RightTab>('holders');
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [isInfoModalOpen, setIsInfoModalOpen] = useState(false);
  const [isIssueModalOpen, setIsIssueModalOpen] = useState(false);
  const [issueForm, setIssueForm] = useState({ recipient: '', amount: '', reason: '' });
  const [issueSuccess, setIssueSuccess] = useState<string | null>(null);

  // Load shares data (for capital increases) on mount, then sync right tab
  useEffect(() => {
    setActiveTab('shares' as TokenTabType);
  }, [setActiveTab]);

  useEffect(() => {
    setActiveTab(RIGHT_TAB_TO_HOOK[rightTab]);
  }, [rightTab, setActiveTab]);

  const issueMutation = useMutation({
    mutationFn: () =>
      issueCompanyShares(apiClient, uuid!, {
        recipient: issueForm.recipient,
        amount: parseInt(issueForm.amount),
        reason: issueForm.reason || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['token', uuid] });
      queryClient.invalidateQueries({ queryKey: ['token', uuid, 'holders'] });
      queryClient.invalidateQueries({ queryKey: ['token', uuid, 'issuances'] });
      setIsIssueModalOpen(false);
      setIssueForm({ recipient: '', amount: '', reason: '' });
      setIssueSuccess('Shares issued successfully');
      setTimeout(() => setIssueSuccess(null), 3000);
    },
  });

  const issueErrorMessage = issueMutation.error
    ? (issueMutation.error as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail ||
      (issueMutation.error as { response?: { data?: { error?: string } } })?.response?.data?.error ||
      (issueMutation.error as { message?: string })?.message ||
      'Failed to issue shares. Please try again.'
    : null;

  const isIssueValid =
    issueForm.recipient.trim() !== '' && issueForm.amount.trim() !== '' && parseInt(issueForm.amount) > 0;

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  if (isLoading) {
    return (
      <PageWrapper>
        <div className="animate-pulse space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="h-64 bg-surface-raised rounded-xl border border-border" />
            <div className="h-64 bg-surface-raised rounded-xl border border-border" />
          </div>
        </div>
      </PageWrapper>
    );
  }

  if (error || !token) {
    return (
      <PageWrapper>
        <div className="bg-surface-raised rounded-xl border border-border p-12 text-center">
          <WarningIcon size={48} className="text-error-light mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-text-primary mb-2">Token Not Found</h3>
          <p className="text-text-muted">The token doesn&apos;t exist or you don&apos;t have permission to view it.</p>
        </div>
      </PageWrapper>
    );
  }

  const formattedSupply = parseInt(token.totalSupply).toLocaleString();
  const isDeployed = token.status === 'deployed';

  return (
    <PageWrapper>
      {issueSuccess && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-success-light/15 border border-success-light/25">
          <CheckCircleIcon className="h-5 w-5 text-success-light" weight="fill" />
          <p className="text-sm text-success-light">{issueSuccess}</p>
        </div>
      )}

      {/* Deployment banners */}
      {token.status === 'deploying' && (
        <div className="flex items-center gap-3 p-4 bg-info-light/10 border border-info-light/20 rounded-lg">
          <ClockIcon size={20} className="text-info-light animate-pulse flex-shrink-0" />
          <div>
            <p className="font-medium text-info-light">Deployment in Progress</p>
            <p className="text-sm text-info-light/80">Your token is being deployed to the blockchain.</p>
          </div>
        </div>
      )}
      {token.status === 'draft' && (
        <div className="flex items-center gap-3 p-4 bg-warning-light/10 border border-warning-light/20 rounded-lg">
          <ClockIcon size={20} className="text-warning-light flex-shrink-0" />
          <div>
            <p className="font-medium text-warning-light">Awaiting Deployment</p>
            <p className="text-sm text-warning-light/80">Your token will be deployed after your listing is approved.</p>
          </div>
        </div>
      )}

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Token Overview */}
        <Panel
          title={token.name}
          icon={<CoinIcon size={ICON_MD} />}
          actions={
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsInfoModalOpen(true)}
                className="p-1.5 rounded-lg hover:bg-surface-tertiary transition-colors"
                title="Token details"
              >
                <InfoIcon size={ICON_SM} className="text-text-muted" />
              </button>
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[token.status]}`}
              >
                {STATUS_LABELS[token.status]}
              </span>
            </div>
          }
        >
          <p className="text-xs text-text-muted px-4 -mt-1 mb-2">
            {token.symbol} · {TOKEN_TYPE_LABELS[token.tokenType] || token.tokenType}
          </p>
          <div className="divide-y divide-border-subtle">
            <DetailRow label="Authorized Shares" value={formattedSupply} />
            <DetailRow label="Transferable" value={token.isTransferable ? 'Yes' : 'No'} />
            <DetailRow label="Divisible" value={token.isDivisible ? 'Yes' : 'No'} />
          </div>

          {/* Capital Increases (inline, only if any exist) */}
          {isDeployed && !isLoadingCapitalIncreases && capitalIncreases.length > 0 && (
            <div className="px-4 pt-4">
              <div className="flex items-center gap-1.5 mb-2">
                <TrendUpIcon size={14} className="text-text-muted" />
                <span className="text-xs font-semibold text-text-muted uppercase tracking-wide">
                  Capital Increases ({capitalIncreases.length})
                </span>
              </div>
              <div className="divide-y divide-border-subtle">
                {capitalIncreases.map((req: CapitalIncreaseRequest) => (
                  <div key={req.uuid} className="flex items-center justify-between py-2">
                    <div>
                      <span className="text-sm font-medium text-success-light">
                        +{req.additionalShares.toLocaleString()}
                      </span>
                      <span className="text-xs text-text-muted ml-2">
                        → {req.newAuthorizedTotal.toLocaleString()} total
                      </span>
                    </div>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${CAPITAL_INCREASE_STATUS_COLORS[req.status]}`}
                    >
                      {CAPITAL_INCREASE_STATUS_LABELS[req.status]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Issue Shares button */}
          {isDeployed && (
            <div className="px-4 pt-4 pb-2">
              <button
                onClick={() => setIsIssueModalOpen(true)}
                className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
              >
                Issue Shares
              </button>
            </div>
          )}
        </Panel>

        {/* Right: Shareholders & Issuances */}
        <Panel
          title={rightTab === 'holders' ? `Shareholders (${totalHolders})` : `Issuances (${issuanceCount})`}
          icon={rightTab === 'holders' ? <UsersThreeIcon size={ICON_MD} /> : <ListBulletsIcon size={ICON_MD} />}
          actions={
            <div className="flex rounded-lg border border-border overflow-hidden">
              <button
                onClick={() => setRightTab('holders')}
                className={`px-3 py-1 text-xs font-medium transition-colors ${
                  rightTab === 'holders'
                    ? 'bg-brand-mid/15 text-brand-light'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                Holders
              </button>
              <button
                onClick={() => setRightTab('issuances')}
                className={`px-3 py-1 text-xs font-medium border-l border-border transition-colors ${
                  rightTab === 'issuances'
                    ? 'bg-brand-mid/15 text-brand-light'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                Issuances
              </button>
            </div>
          }
        >
          {rightTab === 'holders' && (
            <>
              {isLoadingHolders ? (
                <Spinner />
              ) : holders.length > 0 ? (
                <div className="-mx-4 -mb-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="px-4 py-2.5 text-left font-medium text-text-muted text-xs">Address</th>
                        <th className="px-4 py-2.5 text-right font-medium text-text-muted text-xs">Balance</th>
                        <th className="px-4 py-2.5 text-right font-medium text-text-muted text-xs">%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {holders.map((holder: TokenHolder) => (
                        <tr key={holder.address} className="border-b border-border last:border-b-0">
                          <td className="px-4 py-2.5">
                            <div className="flex items-center gap-1.5">
                              <code className="text-xs font-mono text-text-primary">
                                {holder.address.slice(0, 8)}...{holder.address.slice(-6)}
                              </code>
                              <button
                                onClick={() => copyToClipboard(holder.address, holder.address)}
                                className="text-text-muted hover:text-text-primary transition-colors"
                              >
                                <CopiedIcon copied={copiedField === holder.address} />
                              </button>
                            </div>
                            {holder.name && <span className="block text-xs text-text-muted">{holder.name}</span>}
                          </td>
                          <td className="px-4 py-2.5 text-right text-sm font-medium text-text-primary">
                            {parseInt(holder.balance).toLocaleString()}
                          </td>
                          <td className="px-4 py-2.5 text-right text-xs text-text-muted">
                            {holder.percentage.toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8">
                  <UsersThreeIcon size={36} className="text-text-muted mx-auto mb-3" />
                  <h4 className="text-sm font-medium text-text-primary mb-1">No Shareholders Yet</h4>
                  <p className="text-xs text-text-muted">Issue shares to add holders.</p>
                </div>
              )}
            </>
          )}

          {rightTab === 'issuances' && (
            <>
              {isLoadingIssuances ? (
                <Spinner />
              ) : issuances.length > 0 ? (
                <div className="-mx-4 -mb-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="px-4 py-2.5 text-left font-medium text-text-muted text-xs">Date</th>
                        <th className="px-4 py-2.5 text-left font-medium text-text-muted text-xs">Recipient</th>
                        <th className="px-4 py-2.5 text-right font-medium text-text-muted text-xs">Amount</th>
                        <th className="px-4 py-2.5 text-left font-medium text-text-muted text-xs">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {issuances.map((issuance: TokenIssuance) => (
                        <tr key={issuance.uuid} className="border-b border-border last:border-b-0">
                          <td className="px-4 py-2.5 text-xs text-text-muted">
                            {new Date(issuance.createdAt).toLocaleDateString()}
                          </td>
                          <td className="px-4 py-2.5">
                            <div className="flex items-center gap-1.5">
                              <code className="text-xs font-mono text-text-primary">
                                {issuance.recipientAddress.slice(0, 8)}...{issuance.recipientAddress.slice(-6)}
                              </code>
                              <button
                                onClick={() => copyToClipboard(issuance.recipientAddress, `issuance-${issuance.uuid}`)}
                                className="text-text-muted hover:text-text-primary transition-colors"
                              >
                                <CopiedIcon copied={copiedField === `issuance-${issuance.uuid}`} />
                              </button>
                            </div>
                          </td>
                          <td className="px-4 py-2.5 text-right text-sm font-medium text-text-primary">
                            {parseInt(issuance.amount).toLocaleString()}
                          </td>
                          <td className="px-4 py-2.5">
                            <span
                              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                                issuance.status === 'completed'
                                  ? 'bg-success-light/20 text-success-light'
                                  : issuance.status === 'failed'
                                    ? 'bg-error-light/20 text-error-light'
                                    : issuance.status === 'processing'
                                      ? 'bg-info-light/20 text-info-light'
                                      : 'bg-surface-tertiary text-text-muted'
                              }`}
                            >
                              {issuance.statusDisplay}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-8">
                  <ListBulletsIcon size={36} className="text-text-muted mx-auto mb-3" />
                  <h4 className="text-sm font-medium text-text-primary mb-1">No Issuances Yet</h4>
                  <p className="text-xs text-text-muted">Issue shares to see history here.</p>
                </div>
              )}
            </>
          )}
        </Panel>
      </div>

      {/* Info modal */}
      <Modal isOpen={isInfoModalOpen} onClose={() => setIsInfoModalOpen(false)} title="Token Information">
        <div className="divide-y divide-border-subtle">
          <DetailRow label="Name" value={token.name} />
          <DetailRow label="Symbol" value={token.symbol} />
          <DetailRow label="Type" value={TOKEN_TYPE_LABELS[token.tokenType] || token.tokenType} />
          <DetailRow label="Status" value={STATUS_LABELS[token.status]} />
          <DetailRow label="Authorized Shares" value={formattedSupply} />
          <DetailRow label="Decimals" value={String(token.decimals)} />
          <DetailRow label="Transferable" value={token.isTransferable ? 'Yes' : 'No'} />
          <DetailRow label="Divisible" value={token.isDivisible ? 'Yes' : 'No'} />
          {token.contractAddress && (
            <div className="flex items-center justify-between px-4 py-2.5">
              <span className="text-sm text-text-muted">Contract</span>
              <div className="flex items-center gap-2">
                <code className="text-xs font-mono text-text-primary">
                  {token.contractAddress.slice(0, 10)}...{token.contractAddress.slice(-8)}
                </code>
                <button
                  onClick={() => copyToClipboard(token.contractAddress!, 'contractAddress')}
                  className="text-text-muted hover:text-text-primary transition-colors"
                >
                  <CopiedIcon copied={copiedField === 'contractAddress'} />
                </button>
              </div>
            </div>
          )}
          {token.deployedAt && <DetailRow label="Deployed" value={new Date(token.deployedAt).toLocaleString()} />}
        </div>
      </Modal>

      {/* Issue Shares modal */}
      <Modal
        isOpen={isIssueModalOpen}
        onClose={() => {
          setIsIssueModalOpen(false);
          setIssueForm({ recipient: '', amount: '', reason: '' });
          issueMutation.reset();
        }}
        title={`Issue ${token.symbol} Shares`}
        showFooter
        confirmLabel="Issue Shares"
        onConfirm={() => issueMutation.mutate()}
        confirmDisabled={!isIssueValid}
        confirmLoading={issueMutation.isPending}
      >
        <div className="space-y-4">
          {issueErrorMessage && (
            <div className="p-3 rounded-lg bg-error/10 border border-error/30">
              <p className="text-sm text-error-light">{issueErrorMessage}</p>
            </div>
          )}
          <Field>
            <Label className="block text-sm font-medium text-text-primary mb-1">Recipient Address</Label>
            <Input
              type="text"
              placeholder="0x..."
              value={issueForm.recipient}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setIssueForm({ ...issueForm, recipient: e.target.value })
              }
              className="w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid font-mono"
            />
          </Field>
          <Field>
            <Label className="block text-sm font-medium text-text-primary mb-1">Amount</Label>
            <Input
              type="number"
              placeholder="Number of shares"
              min="1"
              value={issueForm.amount}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setIssueForm({ ...issueForm, amount: e.target.value })
              }
              className="w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            />
          </Field>
          <Field>
            <Label className="block text-sm font-medium text-text-primary mb-1">Reason (optional)</Label>
            <Input
              type="text"
              placeholder="e.g. Initial allocation"
              value={issueForm.reason}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setIssueForm({ ...issueForm, reason: e.target.value })
              }
              className="w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            />
          </Field>
        </div>
      </Modal>
    </PageWrapper>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-sm text-text-muted">{label}</span>
      <span className="text-sm font-medium text-text-primary">{value}</span>
    </div>
  );
}
