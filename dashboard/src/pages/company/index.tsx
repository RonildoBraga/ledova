import { PageWrapper } from './components/PageWrapper';
import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Field, Label, Input } from '@headlessui/react';
import {
  BuildingsIcon,
  CoinIcon,
  PencilSimpleIcon,
  CheckCircleIcon,
  WarningIcon,
  PlusIcon,
  CopyIcon,
  InfoIcon,
  UsersThreeIcon,
  ListBulletsIcon,
} from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import { Modal } from '@components/Modal';
import { DESIGN_TOKENS, updateCompany, issueCompanyShares } from '@ledova/shared';
import { useCompany } from './hooks/useCompany';
import { useTokensList, useTokenDetail } from './hooks/useTokens';
import type {
  Company,
  CompanyUpdate,
  CompanyStatus,
  CompanyShareToken as ShareToken,
  TokenStatus,
  TokenType,
  TokenCreate,
  TokenTabType,
  TokenHolder,
  TokenIssuance,
} from '@ledova/shared';
import apiClient from '@services/apiClient';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;
const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;
const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;

const STATUS_LABELS: Record<CompanyStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  review: 'Under Review',
  info_required: 'Info Required',
  approved: 'Approved',
  active: 'Active',
  warning: 'Warning',
  suspended: 'Suspended',
  delisted: 'Delisted',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
};

const STATUS_BADGE_COLORS: Record<CompanyStatus, string> = {
  draft: 'bg-surface-tertiary text-text-muted',
  submitted: 'bg-info-light/15 text-info-light',
  review: 'bg-info-light/15 text-info-light',
  info_required: 'bg-warning-light/15 text-warning-light',
  approved: 'bg-success-light/15 text-success-light',
  active: 'bg-success-light/15 text-success-light',
  warning: 'bg-warning-light/15 text-warning-light',
  suspended: 'bg-error-light/15 text-error-light',
  delisted: 'bg-error-light/15 text-error-light',
  rejected: 'bg-error-light/15 text-error-light',
  withdrawn: 'bg-surface-tertiary text-text-muted',
};

const TOKEN_STATUS_LABELS: Record<TokenStatus, string> = {
  draft: 'Draft',
  deploying: 'Deploying',
  deployed: 'Deployed',
  paused: 'Paused',
};

const TOKEN_STATUS_COLORS: Record<TokenStatus, string> = {
  draft: 'bg-surface-tertiary text-text-muted',
  deploying: 'bg-info-light/20 text-info-light',
  deployed: 'bg-success-light/20 text-success-light',
  paused: 'bg-error-light/20 text-error-light',
};

const TOKEN_TYPE_LABELS: Record<TokenType, string> = {
  ordinary: 'Ordinary',
  preference: 'Preference',
  redeemable: 'Redeemable',
};

function formatAddress(company: Company): string {
  const parts = [
    company.addressLine1,
    company.addressLine2,
    [company.city, company.state, company.postcode].filter(Boolean).join(' '),
  ].filter(Boolean);
  return parts.join(', ');
}

export default function CompanyPage() {
  const { company, companyUuid, stats, isLoading, error, refetch } = useCompany();
  const tokensList = useTokensList();
  const queryClient = useQueryClient();

  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [formData, setFormData] = useState<CompanyUpdate>({});
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [selectedTokenUuid, setSelectedTokenUuid] = useState<string | null>(null);

  // Create token modal state
  const [newToken, setNewToken] = useState<TokenCreate>({
    name: '',
    symbol: '',
    tokenType: 'ordinary',
    totalSupply: '',
  });

  const mutation = useMutation({
    mutationFn: (data: CompanyUpdate) => updateCompany(apiClient, companyUuid!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company'] });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      setIsEditModalOpen(false);
      setSuccessMessage('Company profile updated successfully');
      setTimeout(() => setSuccessMessage(null), 3000);
    },
  });

  const handleEdit = () => {
    if (!company) return;
    setFormData({
      name: company.name || '',
      tradingName: company.tradingName || '',
      addressLine1: company.addressLine1 || '',
      addressLine2: company.addressLine2 || '',
      city: company.city || '',
      state: company.state || '',
      postcode: company.postcode || '',
      phone: company.phone || '',
    });
    setIsEditModalOpen(true);
  };

  const handleSave = () => {
    mutation.mutate(formData);
  };

  const handleFormChange = (field: keyof CompanyUpdate, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleCreateToken = async () => {
    try {
      await tokensList.createToken({ ...newToken, company: companyUuid });
      setNewToken({ name: '', symbol: '', tokenType: 'ordinary', totalSupply: '' });
    } catch {
      // Error handled by mutation state
    }
  };

  const handleCloseCreateModal = () => {
    tokensList.setIsCreateModalOpen(false);
    setNewToken({ name: '', symbol: '', tokenType: 'ordinary', totalSupply: '' });
    tokensList.resetCreateError();
  };

  const createErrorMessage = tokensList.createError
    ? (tokensList.createError as { response?: { data?: { detail?: string; error?: string } } })?.response?.data
        ?.detail ||
      (tokensList.createError as { response?: { data?: { error?: string } } })?.response?.data?.error ||
      (tokensList.createError as { message?: string })?.message ||
      'Failed to create token. Please try again.'
    : null;

  const isCreateValid =
    newToken.name.trim() !== '' &&
    newToken.symbol.trim() !== '' &&
    newToken.totalSupply.trim() !== '' &&
    parseInt(newToken.totalSupply) > 0;

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

  if (error) {
    return (
      <PageWrapper>
        <div className="bg-surface-raised rounded-xl border border-border p-8 text-center">
          <WarningIcon className="h-10 w-10 text-error-light mx-auto mb-3" weight="duotone" />
          <p className="text-text-secondary mb-4">Failed to load company information.</p>
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-mid px-4 py-2 text-sm font-medium text-white hover:bg-brand transition-colors"
          >
            Retry
          </button>
        </div>
      </PageWrapper>
    );
  }

  if (!company) {
    return (
      <PageWrapper>
        <div className="bg-surface-raised rounded-xl border border-border p-8 text-center">
          <BuildingsIcon size={ICON_XL} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-secondary">No company information available.</p>
        </div>
      </PageWrapper>
    );
  }

  const address = formatAddress(company);

  return (
    <PageWrapper>
      {successMessage && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-success-light/15 border border-success-light/25">
          <CheckCircleIcon className="h-5 w-5 text-success-light" weight="fill" />
          <p className="text-sm text-success-light">{successMessage}</p>
        </div>
      )}

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Company Profile */}
        <Panel
          title={company.name}
          icon={<BuildingsIcon size={ICON_MD} />}
          actions={
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_BADGE_COLORS[company.status] || STATUS_BADGE_COLORS.draft}`}
            >
              {STATUS_LABELS[company.status] || company.status}
            </span>
          }
        >
          {company.tradingName && company.tradingName !== company.name && (
            <p className="text-xs text-text-muted px-4 -mt-1 mb-2">Trading as {company.tradingName}</p>
          )}
          <div className="divide-y divide-border-subtle">
            <DetailRow label="Type" value={company.companyTypeDisplay || company.companyType} />
            <DetailRow label="ACN" value={company.acn} mono />
            {company.abn && <DetailRow label="ABN" value={company.abn} mono />}
            {company.email && <DetailRow label="Email" value={company.email} />}
            {company.phone && <DetailRow label="Phone" value={company.phone} />}
            {address && <DetailRow label="Address" value={address} />}
          </div>
          <div className="px-4 pt-4 pb-2">
            <button
              onClick={handleEdit}
              className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
            >
              <PencilSimpleIcon size={ICON_SM} />
              Edit Company
            </button>
          </div>
        </Panel>

        {/* Right: Share Tokens */}
        <Panel title={`Share Tokens${stats ? ` (${stats.totalTokens})` : ''}`} icon={<CoinIcon size={ICON_MD} />}>
          {tokensList.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
            </div>
          ) : tokensList.totalCount === 0 ? (
            <div className="py-8 text-center px-4">
              <div className="mx-auto h-14 w-14 rounded-full bg-brand/10 flex items-center justify-center mb-3">
                <CoinIcon size={ICON_LG} className="text-brand-mid" />
              </div>
              <h4 className="text-sm font-semibold text-text-primary mb-1">No Share Tokens Yet</h4>
              <p className="text-xs text-text-muted mb-4">Create your first token to begin issuing shares.</p>
              <button
                onClick={() => tokensList.setIsCreateModalOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-hover transition-colors"
              >
                <PlusIcon size={ICON_SM} weight="bold" />
                Create Share Token
              </button>
            </div>
          ) : (
            <>
              <div className="divide-y divide-border-subtle">
                {tokensList.tokens.map((token: ShareToken) => (
                  <button
                    key={token.uuid}
                    onClick={() => setSelectedTokenUuid(token.uuid)}
                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-raised/50 transition-colors text-left"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-text-primary truncate">{token.name}</p>
                      <p className="text-xs text-text-muted">
                        {token.symbol} · {TOKEN_TYPE_LABELS[token.tokenType] || token.tokenType}
                      </p>
                    </div>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium flex-shrink-0 ${TOKEN_STATUS_COLORS[token.status]}`}
                    >
                      {TOKEN_STATUS_LABELS[token.status]}
                    </span>
                  </button>
                ))}
              </div>
              <div className="px-4 pt-4 pb-2">
                <button
                  onClick={() => tokensList.setIsCreateModalOpen(true)}
                  className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-border px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
                >
                  <PlusIcon size={ICON_SM} weight="bold" />
                  Create Token
                </button>
              </div>
            </>
          )}
        </Panel>
      </div>

      {/* Edit Company Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => {
          setIsEditModalOpen(false);
          setFormData({});
        }}
        title="Edit Company"
        size="lg"
      >
        <EditForm
          formData={formData}
          isSaving={mutation.isPending}
          onFormChange={handleFormChange}
          onSave={handleSave}
          onCancel={() => {
            setIsEditModalOpen(false);
            setFormData({});
          }}
        />
      </Modal>

      {/* Create Token Modal */}
      <Modal
        isOpen={tokensList.isCreateModalOpen}
        onClose={handleCloseCreateModal}
        title="Create Share Token"
        showFooter
        confirmLabel="Create Token"
        onConfirm={handleCreateToken}
        confirmDisabled={!isCreateValid}
        confirmLoading={tokensList.isCreating}
      >
        <div className="space-y-4">
          {createErrorMessage && (
            <div className="p-3 rounded-lg bg-error/10 border border-error/30">
              <p className="text-sm text-error-light">{createErrorMessage}</p>
            </div>
          )}
          <Field>
            <Label className="block text-sm font-medium text-text-primary mb-1">Token Name</Label>
            <Input
              type="text"
              placeholder="e.g. Ordinary Shares"
              value={newToken.name}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewToken({ ...newToken, name: e.target.value })}
              className="w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            />
          </Field>
          <Field>
            <Label className="block text-sm font-medium text-text-primary mb-1">Symbol</Label>
            <Input
              type="text"
              placeholder="e.g. ORD"
              value={newToken.symbol}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setNewToken({ ...newToken, symbol: e.target.value.toUpperCase() })
              }
              className="w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            />
          </Field>
          <Field>
            <Label className="block text-sm font-medium text-text-primary mb-1">Type</Label>
            <select
              value={newToken.tokenType}
              onChange={(e) => setNewToken({ ...newToken, tokenType: e.target.value as TokenType })}
              className="w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            >
              <option value="ordinary">Ordinary</option>
              <option value="preference">Preference</option>
              <option value="redeemable">Redeemable</option>
            </select>
          </Field>
          <Field>
            <Label className="block text-sm font-medium text-text-primary mb-1">Total Supply (Authorized Shares)</Label>
            <Input
              type="number"
              placeholder="e.g. 1000000"
              min="1"
              value={newToken.totalSupply}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setNewToken({ ...newToken, totalSupply: e.target.value })
              }
              className="w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            />
          </Field>
        </div>
      </Modal>

      {/* Token Detail Modal */}
      {selectedTokenUuid && <TokenDetailModal uuid={selectedTokenUuid} onClose={() => setSelectedTokenUuid(null)} />}
    </PageWrapper>
  );
}

// --- Token Detail Modal ---

function TokenDetailModal({ uuid, onClose }: { uuid: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const {
    token,
    isLoading,
    setActiveTab,
    holders,
    totalHolders,
    isLoadingHolders,
    issuances,
    issuanceCount,
    isLoadingIssuances,
  } = useTokenDetail(uuid);

  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [isInfoOpen, setIsInfoOpen] = useState(false);
  const [isIssueOpen, setIsIssueOpen] = useState(false);
  const [issueForm, setIssueForm] = useState({ recipient: '', amount: '', reason: '' });

  // Load holders + issuances data
  useEffect(() => {
    setActiveTab('shareholders' as TokenTabType);
    // Small delay then also trigger issuances
    const t = setTimeout(() => setActiveTab('issuances' as TokenTabType), 100);
    return () => clearTimeout(t);
  }, [setActiveTab]);

  const issueMutation = useMutation({
    mutationFn: () =>
      issueCompanyShares(apiClient, uuid, {
        recipient: issueForm.recipient,
        amount: parseInt(issueForm.amount),
        reason: issueForm.reason || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['token', uuid] });
      setIsIssueOpen(false);
      setIssueForm({ recipient: '', amount: '', reason: '' });
    },
  });

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const isIssueValid =
    issueForm.recipient.trim() !== '' && issueForm.amount.trim() !== '' && parseInt(issueForm.amount) > 0;

  if (isLoading || !token) {
    return (
      <Modal isOpen onClose={onClose} size="2xl">
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 border-4 border-brand-subtle border-t-brand rounded-full animate-spin" />
        </div>
      </Modal>
    );
  }

  const formattedSupply = parseInt(token.totalSupply).toLocaleString();
  const isDeployed = token.status === 'deployed';

  // Info sub-modal
  if (isInfoOpen) {
    return (
      <Modal isOpen onClose={() => setIsInfoOpen(false)} title="Token Details">
        <div className="divide-y divide-border-subtle">
          <DetailRow label="Name" value={token.name} />
          <DetailRow label="Symbol" value={token.symbol} />
          <DetailRow label="Type" value={TOKEN_TYPE_LABELS[token.tokenType] || token.tokenType} />
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
                  onClick={() => copyToClipboard(token.contractAddress!, 'contract')}
                  className="text-text-muted hover:text-text-primary transition-colors"
                >
                  {copiedField === 'contract' ? (
                    <CheckCircleIcon size={ICON_SM} className="text-success-light" />
                  ) : (
                    <CopyIcon size={ICON_SM} />
                  )}
                </button>
              </div>
            </div>
          )}
          {token.deployedAt && <DetailRow label="Deployed" value={new Date(token.deployedAt).toLocaleString()} />}
        </div>
      </Modal>
    );
  }

  // Issue sub-modal
  if (isIssueOpen) {
    return (
      <Modal
        isOpen
        onClose={() => {
          setIsIssueOpen(false);
          setIssueForm({ recipient: '', amount: '', reason: '' });
          issueMutation.reset();
        }}
        title={`Request ${token.symbol} Issuance`}
        showFooter
        confirmLabel="Request Issuance"
        onConfirm={() => issueMutation.mutate()}
        confirmDisabled={!isIssueValid}
        confirmLoading={issueMutation.isPending}
      >
        <div className="space-y-4">
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
    );
  }

  // Main token detail modal
  return (
    <Modal isOpen onClose={onClose} size="2xl">
      <div className="space-y-5">
        {/* Hero header */}
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-brand-mid/15 flex items-center justify-center flex-shrink-0">
            <CoinIcon size={ICON_LG} className="text-brand-light" weight="duotone" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <h2 className="text-lg font-bold text-text-primary truncate">{token.name}</h2>
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium flex-shrink-0 ${TOKEN_STATUS_COLORS[token.status]}`}
              >
                {TOKEN_STATUS_LABELS[token.status]}
              </span>
            </div>
            <p className="text-sm text-text-muted">
              {token.symbol} · {TOKEN_TYPE_LABELS[token.tokenType] || token.tokenType} ·{' '}
              <span className="font-medium text-text-primary">{formattedSupply}</span> shares
            </p>
          </div>
        </div>

        {/* Cap Table */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-1.5">
              <UsersThreeIcon size={ICON_SM} className="text-text-muted" />
              Cap Table
              <span className="text-text-muted font-normal">({totalHolders})</span>
            </h3>
          </div>
          {isLoadingHolders ? (
            <div className="py-4 text-center">
              <div className="h-5 w-5 border-2 border-brand-subtle border-t-brand rounded-full animate-spin mx-auto" />
            </div>
          ) : holders.length > 0 ? (
            <div className="bg-surface-tertiary/50 rounded-lg border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-3 py-2 text-left text-xs font-medium text-text-muted">Holder</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-text-muted">Shares</th>
                    <th className="px-3 py-2 text-right text-xs font-medium text-text-muted">Ownership</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {holders.map((h: TokenHolder) => (
                    <tr key={h.address}>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1.5">
                          {h.name && <span className="text-sm text-text-primary">{h.name}</span>}
                          <code className={`text-xs font-mono ${h.name ? 'text-text-muted' : 'text-text-primary'}`}>
                            {h.address.slice(0, 6)}...{h.address.slice(-4)}
                          </code>
                          <button
                            onClick={() => copyToClipboard(h.address, h.address)}
                            className="text-text-muted hover:text-text-primary transition-colors"
                          >
                            {copiedField === h.address ? (
                              <CheckCircleIcon size={ICON_SM} className="text-success-light" />
                            ) : (
                              <CopyIcon size={ICON_SM} />
                            )}
                          </button>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-right font-medium text-text-primary tabular-nums">
                        {parseInt(h.balance).toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right text-text-muted tabular-nums">{h.percentage.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="bg-surface-tertiary/30 rounded-lg border border-border-subtle py-6 text-center">
              <UsersThreeIcon size={ICON_LG} className="text-text-muted mx-auto mb-2" />
              <p className="text-sm text-text-muted">
                {isDeployed
                  ? 'No shareholders yet. Issue shares to get started.'
                  : 'Deploy the token to track holders.'}
              </p>
            </div>
          )}
        </div>

        {/* Recent Issuances */}
        <div>
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-1.5 mb-2">
            <ListBulletsIcon size={ICON_SM} className="text-text-muted" />
            Recent Issuances
            <span className="text-text-muted font-normal">({issuanceCount})</span>
          </h3>
          {isLoadingIssuances ? (
            <div className="py-4 text-center">
              <div className="h-5 w-5 border-2 border-brand-subtle border-t-brand rounded-full animate-spin mx-auto" />
            </div>
          ) : issuances.length > 0 ? (
            <div className="bg-surface-tertiary/50 rounded-lg border border-border divide-y divide-border-subtle">
              {issuances.slice(0, 5).map((iss: TokenIssuance) => (
                <div key={iss.uuid} className="flex items-center gap-3 px-3 py-2.5">
                  <span className="text-xs text-text-muted w-20 flex-shrink-0">
                    {new Date(iss.createdAt).toLocaleDateString()}
                  </span>
                  <span className="text-xs text-text-muted">→</span>
                  <code className="text-xs font-mono text-text-primary">
                    {iss.recipientAddress.slice(0, 6)}...{iss.recipientAddress.slice(-4)}
                  </code>
                  <span className="text-sm font-semibold text-success-light ml-auto tabular-nums">
                    +{parseInt(iss.amount).toLocaleString()}
                  </span>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      iss.status === 'completed'
                        ? 'bg-success-light/20 text-success-light'
                        : iss.status === 'failed'
                          ? 'bg-error-light/20 text-error-light'
                          : iss.status === 'processing'
                            ? 'bg-info-light/20 text-info-light'
                            : 'bg-surface-tertiary text-text-muted'
                    }`}
                  >
                    {iss.statusDisplay}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-surface-tertiary/30 rounded-lg border border-border-subtle py-6 text-center">
              <ListBulletsIcon size={ICON_LG} className="text-text-muted mx-auto mb-2" />
              <p className="text-sm text-text-muted">No issuances yet.</p>
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 pt-1">
          {isDeployed && (
            <button
              onClick={() => setIsIssueOpen(true)}
              className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-brand-mid px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand transition-colors"
            >
              Request Issuance
            </button>
          )}
          <button
            onClick={() => setIsInfoOpen(true)}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
          >
            <InfoIcon size={ICON_SM} className="text-text-muted" />
            Token Details
          </button>
        </div>
      </div>
    </Modal>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5">
      <span className="text-sm text-text-muted">{label}</span>
      <span className={`text-sm text-text-primary font-medium ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  );
}

function EditForm({
  formData,
  isSaving,
  onFormChange,
  onSave,
  onCancel,
}: {
  formData: CompanyUpdate;
  isSaving: boolean;
  onFormChange: (field: keyof CompanyUpdate, value: string) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      <Field>
        <Label className="text-sm font-medium text-text-secondary">Company Name</Label>
        <Input
          className="mt-1 block w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
          value={formData.name || ''}
          onChange={(e) => onFormChange('name', e.target.value)}
        />
      </Field>
      <Field>
        <Label className="text-sm font-medium text-text-secondary">Trading Name</Label>
        <Input
          className="mt-1 block w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
          value={formData.tradingName || ''}
          onChange={(e) => onFormChange('tradingName', e.target.value)}
          placeholder="Optional trading name"
        />
      </Field>
      <Field>
        <Label className="text-sm font-medium text-text-secondary">Address Line 1</Label>
        <Input
          className="mt-1 block w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
          value={formData.addressLine1 || ''}
          onChange={(e) => onFormChange('addressLine1', e.target.value)}
        />
      </Field>
      <Field>
        <Label className="text-sm font-medium text-text-secondary">Address Line 2</Label>
        <Input
          className="mt-1 block w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
          value={formData.addressLine2 || ''}
          onChange={(e) => onFormChange('addressLine2', e.target.value)}
          placeholder="Optional"
        />
      </Field>
      <div className="grid grid-cols-3 gap-4">
        <Field>
          <Label className="text-sm font-medium text-text-secondary">City</Label>
          <Input
            className="mt-1 block w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-text-primary focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            value={formData.city || ''}
            onChange={(e) => onFormChange('city', e.target.value)}
          />
        </Field>
        <Field>
          <Label className="text-sm font-medium text-text-secondary">State</Label>
          <Input
            className="mt-1 block w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-text-primary focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            value={formData.state || ''}
            onChange={(e) => onFormChange('state', e.target.value)}
          />
        </Field>
        <Field>
          <Label className="text-sm font-medium text-text-secondary">Postcode</Label>
          <Input
            className="mt-1 block w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-text-primary focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            value={formData.postcode || ''}
            onChange={(e) => onFormChange('postcode', e.target.value)}
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field>
          <Label className="text-sm font-medium text-text-secondary">Phone</Label>
          <Input
            className="mt-1 block w-full rounded-lg border border-border bg-surface-tertiary px-3 py-2 text-text-primary focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            value={formData.phone || ''}
            onChange={(e) => onFormChange('phone', e.target.value)}
          />
        </Field>
      </div>
      <div className="flex justify-end gap-3 pt-4">
        <button
          onClick={onCancel}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={onSave}
          disabled={isSaving}
          className="rounded-lg bg-brand-mid px-6 py-2 text-sm font-medium text-white hover:bg-brand disabled:opacity-50 transition-colors"
        >
          {isSaving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  );
}
