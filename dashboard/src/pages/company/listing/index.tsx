import { PageWrapper } from '../components/PageWrapper';
import { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  WarningIcon,
  CheckCircleIcon,
  UploadSimpleIcon,
  TrashIcon,
  ArrowLeftIcon,
  InfoIcon,
  EyeIcon,
  XIcon,
  FileIcon,
  ClockIcon,
  XCircleIcon,
} from '@phosphor-icons/react';
import { Panel } from '@components/Panel';
import { Modal } from '@components/Modal';
import { useCompany } from '../hooks/useCompany';
import {
  getCompanyDocuments,
  uploadCompanyDocument,
  deleteCompanyDocument,
  submitApplication,
  resubmitApplication,
  withdrawApplication,
  getOperator,
  getErrorMessage,
  CACHE_TIMING,
} from '@ledova/shared';
import type { Company, CompanyDocument, DocumentType } from '@ledova/shared';
import apiClient from '@services/apiClient';

const REQUIRED_DOCUMENTS: { type: DocumentType; label: string }[] = [
  { type: 'cert_inc', label: 'Certificate of Incorporation' },
  { type: 'asic', label: 'ASIC Company Extract' },
  { type: 'constitution', label: 'Company Constitution' },
  { type: 'share_register', label: 'Current Share Register' },
  { type: 'financials', label: 'Financial Statements' },
  { type: 'director_id', label: 'Director Identification' },
  { type: 'beneficial_ownership', label: 'Beneficial Ownership Declaration' },
  { type: 'business_plan', label: 'Business Plan' },
  { type: 'risk_disclosure', label: 'Risk Disclosure Statement' },
];

const OPTIONAL_DOCUMENTS: { type: DocumentType; label: string }[] = [
  { type: 'auditor_report', label: 'Auditor Report' },
  { type: 'shareholder', label: 'Shareholder Agreement' },
  { type: 'prospectus', label: 'Prospectus' },
  { type: 'legal_opinion', label: 'Legal Opinion' },
  { type: 'tax_return', label: 'Tax Return' },
  { type: 'bank_statement', label: 'Bank Statement' },
];

const WITHDRAWABLE_STATUSES: Company['status'][] = ['submitted', 'info_required'];

const ACTION_ERROR_FALLBACK = 'The request was refused. Please try again.';

export default function ListingPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { company, companyUuid, isLoading: isLoadingCompany } = useCompany();
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [selectedDocType, setSelectedDocType] = useState<DocumentType | null>(null);
  const [infoResponse, setInfoResponse] = useState('');
  const [withdrawModalOpen, setWithdrawModalOpen] = useState(false);
  const [withdrawReason, setWithdrawReason] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  const { data: docsData, isLoading: isLoadingDocs } = useQuery({
    queryKey: ['company-documents', companyUuid],
    queryFn: () => getCompanyDocuments(apiClient, companyUuid!),
    enabled: !!companyUuid,
    refetchInterval: CACHE_TIMING.SIGNED_URL_REFETCH_INTERVAL,
  });

  const { data: operatorData } = useQuery({
    queryKey: ['operator'],
    queryFn: () => getOperator(apiClient),
    staleTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });
  const operatorName = operatorData?.data?.name || 'The operator';

  const documents = docsData?.data?.results || [];

  const invalidateCompany = () => {
    queryClient.invalidateQueries({ queryKey: ['company', companyUuid] });
    queryClient.invalidateQueries({ queryKey: ['companies'] });
  };
  const surfaceError = (error: unknown) => setActionError(getErrorMessage(error, ACTION_ERROR_FALLBACK));

  const submitMutation = useMutation({
    mutationFn: () => submitApplication(apiClient, companyUuid!),
    onMutate: () => setActionError(null),
    onSuccess: invalidateCompany,
    onError: surfaceError,
  });

  const resubmitMutation = useMutation({
    mutationFn: () => resubmitApplication(apiClient, companyUuid!, { response: infoResponse.trim() }),
    onMutate: () => setActionError(null),
    onSuccess: () => {
      setInfoResponse('');
      invalidateCompany();
    },
    onError: surfaceError,
  });

  const withdrawMutation = useMutation({
    mutationFn: () => withdrawApplication(apiClient, companyUuid!, { reason: withdrawReason.trim() }),
    onMutate: () => setActionError(null),
    onSuccess: () => {
      setWithdrawModalOpen(false);
      setWithdrawReason('');
      invalidateCompany();
    },
    onError: (error: unknown) => {
      setWithdrawModalOpen(false);
      surfaceError(error);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (docUuid: string) => deleteCompanyDocument(apiClient, companyUuid!, docUuid),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['company-documents', companyUuid] }),
  });

  const isLoading = isLoadingCompany || isLoadingDocs;
  const status = company?.status;
  const isInfoRequired = status === 'info_required';
  const canEdit = status === 'draft' || isInfoRequired;
  const canWithdraw = !!status && WITHDRAWABLE_STATUSES.includes(status);
  const uploadedTypes = new Set(documents.map((d: CompanyDocument) => d.documentType));
  const missingRequired = REQUIRED_DOCUMENTS.filter((d) => !uploadedTypes.has(d.type));
  const hasRequiredDocuments = missingRequired.length === 0;
  const canSubmit = status === 'draft' && hasRequiredDocuments;
  const canResubmit = isInfoRequired && hasRequiredDocuments && infoResponse.trim() !== '';
  const isActing = submitMutation.isPending || resubmitMutation.isPending || withdrawMutation.isPending;

  if (isLoading) {
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
        <button
          onClick={() => navigate('/company')}
          className="mt-4 text-brand-light hover:text-brand-subtle font-medium"
        >
          Go to Company
        </button>
      </div>
    );
  }

  const withdrawModal = (
    <Modal
      isOpen={withdrawModalOpen}
      onClose={() => setWithdrawModalOpen(false)}
      title="Withdraw Application"
      showFooter
      confirmLabel={withdrawMutation.isPending ? 'Withdrawing...' : 'Withdraw Application'}
      onConfirm={() => withdrawMutation.mutate()}
      confirmDisabled={withdrawMutation.isPending}
      confirmLoading={withdrawMutation.isPending}
    >
      <div className="space-y-3">
        <p className="text-sm text-text-secondary">
          Withdrawing takes your application out of the review queue. You will need to register again to list your
          company later.
        </p>
        <label className="block">
          <span className="text-sm font-medium text-text-primary">Reason (optional)</span>
          <textarea
            value={withdrawReason}
            onChange={(e) => setWithdrawReason(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
            placeholder="Let the operator know why you are withdrawing"
          />
        </label>
      </div>
    </Modal>
  );

  const errorBanner = actionError && (
    <div className="flex items-start gap-3 p-4 rounded-lg bg-error-light/10 border border-error-light/30">
      <XCircleIcon size={20} className="text-error-light flex-shrink-0 mt-0.5" weight="fill" />
      <p className="text-sm text-error-light">{actionError}</p>
    </div>
  );

  if (!canEdit) {
    return (
      <PageWrapper>
        {errorBanner}
        <Panel>
          <ApplicationStatusView
            company={company}
            operatorName={operatorName}
            canWithdraw={canWithdraw}
            onWithdraw={() => setWithdrawModalOpen(true)}
          />
        </Panel>
        {withdrawModal}
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      {errorBanner}

      {isInfoRequired && (
        <div className="flex items-start gap-3 p-4 rounded-lg bg-warning-light/10 border border-warning-light/30">
          <WarningIcon size={20} className="text-warning-light flex-shrink-0 mt-0.5" weight="fill" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-warning-light">Additional Information Required</p>
            {company.infoRequestReason && (
              <p className="text-sm text-warning-light opacity-80 mt-1 whitespace-pre-wrap">
                {company.infoRequestReason}
              </p>
            )}
            {company.additionalInfoResponse && (
              <div className="mt-3 rounded-lg bg-surface-raised/60 border border-border-subtle p-3">
                <p className="text-xs font-medium text-text-muted mb-1">Your previous response</p>
                <p className="text-sm text-text-secondary whitespace-pre-wrap">{company.additionalInfoResponse}</p>
              </div>
            )}
          </div>
        </div>
      )}

      <Panel title="Required Documents">
        <div className="divide-y divide-border-subtle">
          {REQUIRED_DOCUMENTS.map((doc) => {
            const uploaded = documents.find((d: CompanyDocument) => d.documentType === doc.type);
            return (
              <div key={doc.type} className="px-6 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  {uploaded ? (
                    <CheckCircleIcon size={20} className="text-success-light flex-shrink-0" weight="fill" />
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-border flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <span className="text-sm text-text-primary block">{doc.label}</span>
                    {uploaded && <span className="text-xs text-text-muted block truncate">{uploaded.name}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {uploaded ? (
                    <>
                      {uploaded.fileUrl && (
                        <a
                          href={uploaded.fileUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-light hover:text-brand-subtle p-1"
                        >
                          <EyeIcon size={16} />
                        </a>
                      )}
                      <button
                        onClick={() => deleteMutation.mutate(uploaded.uuid)}
                        className="text-error-light hover:text-error-light p-1"
                        disabled={deleteMutation.isPending}
                      >
                        <TrashIcon size={16} />
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => {
                        setSelectedDocType(doc.type);
                        setUploadModalOpen(true);
                      }}
                      className="text-brand-light hover:text-brand-subtle p-1"
                    >
                      <UploadSimpleIcon size={16} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title="Optional Documents">
        <div className="divide-y divide-border-subtle">
          {OPTIONAL_DOCUMENTS.map((doc) => {
            const uploaded = documents.find((d: CompanyDocument) => d.documentType === doc.type);
            return (
              <div key={doc.type} className="px-6 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  {uploaded ? (
                    <CheckCircleIcon size={20} className="text-success-light flex-shrink-0" weight="fill" />
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-border flex-shrink-0" />
                  )}
                  <div className="min-w-0">
                    <span className="text-sm text-text-primary block">{doc.label}</span>
                    {uploaded && <span className="text-xs text-text-muted block truncate">{uploaded.name}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {uploaded ? (
                    <>
                      {uploaded.fileUrl && (
                        <a
                          href={uploaded.fileUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-light hover:text-brand-subtle p-1"
                        >
                          <EyeIcon size={16} />
                        </a>
                      )}
                      <button
                        onClick={() => deleteMutation.mutate(uploaded.uuid)}
                        className="text-error-light hover:text-error-light p-1"
                        disabled={deleteMutation.isPending}
                      >
                        <TrashIcon size={16} />
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => {
                        setSelectedDocType(doc.type);
                        setUploadModalOpen(true);
                      }}
                      className="text-brand-light hover:text-brand-subtle p-1"
                    >
                      <UploadSimpleIcon size={16} />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      {isInfoRequired && (
        <Panel title="Your Response">
          <div className="px-6 py-4 space-y-2">
            <p className="text-sm text-text-secondary">
              Answer the request above, upload any documents it asks for, then resubmit your application.
            </p>
            <textarea
              value={infoResponse}
              onChange={(e) => setInfoResponse(e.target.value)}
              rows={4}
              className="w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid"
              placeholder="Describe what you changed or provide the information requested"
            />
          </div>
        </Panel>
      )}

      <Panel title="What Happens Next" icon={<InfoIcon size={20} />}>
        <div className="px-6 py-4">
          <ol className="list-decimal list-inside space-y-2 text-sm text-text-secondary">
            <li>Submit your application with all required documents</li>
            <li>{operatorName} reviews your application (typically 2-5 business days)</li>
            <li>You may be asked for additional information</li>
            <li>Once approved, you deploy your share token on the blockchain</li>
            <li>Your company is activated on the platform</li>
          </ol>
        </div>
      </Panel>

      <div className="flex items-center justify-between">
        <button
          onClick={() => navigate('/company')}
          className="flex items-center gap-2 text-sm text-text-muted hover:text-text-primary transition-colors"
        >
          <ArrowLeftIcon size={16} />
          Back to Company
        </button>
        <div className="flex items-center gap-4">
          {missingRequired.length > 0 && (
            <span className="text-sm text-error-light">{missingRequired.length} required document(s) missing</span>
          )}
          {canWithdraw && (
            <button
              onClick={() => setWithdrawModalOpen(true)}
              disabled={isActing}
              className="text-sm font-medium text-text-muted hover:text-error-light disabled:opacity-50 transition-colors"
            >
              Withdraw
            </button>
          )}
          {isInfoRequired ? (
            <button
              onClick={() => resubmitMutation.mutate()}
              disabled={!canResubmit || isActing}
              className="bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-2.5 px-6 rounded-lg transition-colors"
            >
              {resubmitMutation.isPending ? 'Resubmitting...' : 'Resubmit Application'}
            </button>
          ) : (
            <button
              onClick={() => submitMutation.mutate()}
              disabled={!canSubmit || isActing}
              className="bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed text-white font-semibold py-2.5 px-6 rounded-lg transition-colors"
            >
              {submitMutation.isPending ? 'Submitting...' : 'Submit Application'}
            </button>
          )}
        </div>
      </div>

      {withdrawModal}

      <UploadModal
        isOpen={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        companyUuid={companyUuid!}
        documentType={selectedDocType}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ['company-documents', companyUuid] });
          setUploadModalOpen(false);
        }}
      />
    </PageWrapper>
  );
}

function ApplicationStatusView({
  company,
  operatorName,
  canWithdraw,
  onWithdraw,
}: {
  company: Company;
  operatorName: string;
  canWithdraw: boolean;
  onWithdraw: () => void;
}) {
  const statusLabel = company.statusDisplay || company.status;
  const outcome = (() => {
    switch (company.status) {
      case 'approved':
      case 'active':
        return {
          icon: <CheckCircleIcon size={48} className="text-success-light mx-auto mb-4" weight="duotone" />,
          title: company.status === 'active' ? 'Company Active' : 'Application Approved',
          body: `Your listing application was approved and your company is ${statusLabel}.`,
        };
      case 'rejected':
        return {
          icon: <XCircleIcon size={48} className="text-error-light mx-auto mb-4" weight="duotone" />,
          title: 'Application Rejected',
          body: company.rejectionReason
            ? `${operatorName} rejected the application: ${company.rejectionReason}`
            : `${operatorName} rejected the application.`,
        };
      case 'withdrawn':
        return {
          icon: <XCircleIcon size={48} className="text-text-muted mx-auto mb-4" weight="duotone" />,
          title: 'Application Withdrawn',
          body: company.withdrawalReason
            ? `You withdrew this application: ${company.withdrawalReason}`
            : 'You withdrew this application.',
        };
      case 'review':
        return {
          icon: <ClockIcon size={48} className="text-info-light mx-auto mb-4" weight="duotone" />,
          title: 'Under Review',
          body: `${operatorName} is reviewing your application. Withdrawal is no longer available once the review has started.`,
        };
      case 'submitted':
        return {
          icon: <ClockIcon size={48} className="text-info-light mx-auto mb-4" weight="duotone" />,
          title: 'Application Submitted',
          body: `Your listing application is waiting for ${operatorName} to start the review.`,
        };
      default:
        return {
          icon: <InfoIcon size={48} className="text-text-muted mx-auto mb-4" weight="duotone" />,
          title: statusLabel,
          body: `Your company is currently ${statusLabel}.`,
        };
    }
  })();

  return (
    <div className="py-8 px-6 text-center">
      {outcome.icon}
      <h3 className="text-lg font-semibold text-text-primary mb-2">{outcome.title}</h3>
      <p className="text-text-muted">{outcome.body}</p>
      {company.additionalInfoResponse && (
        <div className="mt-6 mx-auto max-w-xl text-left rounded-lg bg-surface-raised/60 border border-border-subtle p-4">
          {company.infoRequestReason && (
            <>
              <p className="text-xs font-medium text-text-muted mb-1">Information requested</p>
              <p className="text-sm text-text-secondary whitespace-pre-wrap mb-3">{company.infoRequestReason}</p>
            </>
          )}
          <p className="text-xs font-medium text-text-muted mb-1">Your response</p>
          <p className="text-sm text-text-secondary whitespace-pre-wrap">{company.additionalInfoResponse}</p>
        </div>
      )}
      {canWithdraw && (
        <button
          onClick={onWithdraw}
          className="mt-6 rounded-lg border border-border px-4 py-2 text-sm font-medium text-text-primary hover:bg-surface-tertiary transition-colors"
        >
          Withdraw Application
        </button>
      )}
    </div>
  );
}

function UploadModal({
  isOpen,
  onClose,
  companyUuid,
  documentType,
  onSuccess,
}: {
  isOpen: boolean;
  onClose: () => void;
  companyUuid: string;
  documentType: DocumentType | null;
  onSuccess: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async () => {
    if (!file || !documentType) return;
    setIsUploading(true);
    try {
      await uploadCompanyDocument(apiClient, companyUuid, {
        documentType,
        name: file.name,
        file,
      });
      setFile(null);
      onSuccess();
    } catch {
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const docLabel =
    [...REQUIRED_DOCUMENTS, ...OPTIONAL_DOCUMENTS].find((d) => d.type === documentType)?.label || 'Document';

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        setFile(null);
        onClose();
      }}
      title={`Upload ${docLabel}`}
      showFooter
      confirmLabel={isUploading ? 'Uploading...' : 'Upload'}
      onConfirm={handleUpload}
      confirmDisabled={!file || isUploading}
      confirmLoading={isUploading}
    >
      {!file ? (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className={`flex flex-col items-center justify-center gap-3 py-10 px-6 rounded-lg border-2 border-dashed cursor-pointer transition-colors ${
            isDragging
              ? 'border-brand-light bg-brand-mid/10'
              : 'border-border hover:border-brand-subtle hover:bg-surface-hover'
          }`}
        >
          <UploadSimpleIcon size={32} className="text-text-muted" weight="light" />
          <div className="text-center">
            <p className="text-sm text-text-primary">
              Drag & drop or <span className="text-brand-light font-medium">browse</span>
            </p>
            <p className="text-xs text-text-muted mt-1">PDF or images, max 10 MB</p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,image/*"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="hidden"
          />
        </div>
      ) : (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-surface-hover">
          <FileIcon size={24} className="text-brand-light flex-shrink-0" weight="regular" />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-text-primary truncate">{file.name}</p>
            <p className="text-xs text-text-muted">{formatFileSize(file.size)}</p>
          </div>
          <button onClick={() => setFile(null)} className="text-text-muted hover:text-text-primary p-1 flex-shrink-0">
            <XIcon size={16} />
          </button>
        </div>
      )}
    </Modal>
  );
}
