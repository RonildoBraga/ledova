import { useCallback, useRef, useState } from 'react';
import { FileIcon, UploadSimpleIcon, XIcon } from '@phosphor-icons/react';
import { Modal } from '@components/Modal';
import { getCompanies, getErrorMessage, submitInvestorClassification } from '@ledova/shared';
import type { Company, InvestorCategory } from '@ledova/shared';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@services/apiClient';
import { CATEGORIES, CERTIFIER_BODIES, WHOLESALE_ONLY_NOTICE } from './constants';

const FIELD_CLASS =
  'mt-1 w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary ' +
  'placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid';

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface ClaimModalProps {
  isOpen: boolean;
  onClose: () => void;
  category: InvestorCategory | null;
  userAccount: string | null;
  onSuccess: () => void;
}

export function ClaimModal({ isOpen, onClose, category, userAccount, onSuccess }: ClaimModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [declaredBasis, setDeclaredBasis] = useState('');
  const [company, setCompany] = useState('');
  const [certificateIssuedAt, setCertificateIssuedAt] = useState('');
  const [certifierName, setCertifierName] = useState('');
  const [certifierBody, setCertifierBody] = useState('');
  const [certifierMembershipNumber, setCertifierMembershipNumber] = useState('');
  const [declarationAccepted, setDeclarationAccepted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const needsCompany = category === 'associated_person';
  const needsCertifier = category === 'accountant_certificate';

  const { data: companiesData } = useQuery({
    queryKey: ['companies'],
    queryFn: () => getCompanies(apiClient),
    enabled: isOpen && needsCompany,
  });
  const companies: Company[] = companiesData?.data?.results ?? [];

  const spec = CATEGORIES.find((item) => item.category === category);

  const reset = () => {
    setFile(null);
    setDeclaredBasis('');
    setCompany('');
    setCertificateIssuedAt('');
    setCertifierName('');
    setCertifierBody('');
    setCertifierMembershipNumber('');
    setDeclarationAccepted(false);
    setError(null);
  };

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    setIsDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }, []);

  const isComplete =
    !!file &&
    !!category &&
    !!userAccount &&
    declarationAccepted &&
    declaredBasis.trim() !== '' &&
    (!needsCompany || company !== '') &&
    (!needsCertifier ||
      (certificateIssuedAt !== '' &&
        certifierName.trim() !== '' &&
        certifierBody !== '' &&
        certifierMembershipNumber.trim() !== ''));

  const handleSubmit = async () => {
    if (!isComplete || !file || !category || !userAccount) return;
    setIsSubmitting(true);
    setError(null);
    try {
      await submitInvestorClassification(apiClient, {
        userAccount,
        category,
        declaredBasis: declaredBasis.trim(),
        file,
        company: needsCompany ? company : undefined,
        certificateIssuedAt: needsCertifier ? certificateIssuedAt : undefined,
        certifierName: needsCertifier ? certifierName.trim() : undefined,
        certifierBody: needsCertifier ? (certifierBody as 'ca_anz' | 'cpa_australia' | 'ipa') : undefined,
        certifierMembershipNumber: needsCertifier ? certifierMembershipNumber.trim() : undefined,
      });
      reset();
      onSuccess();
    } catch (caught) {
      setError(getErrorMessage(caught, 'The claim was refused. Please check the details and try again.'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        reset();
        onClose();
      }}
      title={spec ? `Claim: ${spec.label}` : 'Claim'}
      size="lg"
      showFooter
      confirmLabel={isSubmitting ? 'Submitting...' : 'Submit for review'}
      onConfirm={handleSubmit}
      confirmDisabled={!isComplete || isSubmitting}
      confirmLoading={isSubmitting}
    >
      <div className="space-y-4">
        {error && (
          <div className="rounded-lg border border-error-light/30 bg-error-light/10 p-3 text-sm text-error-light">
            {error}
          </div>
        )}

        <p className="text-sm text-text-secondary">{spec?.evidence}</p>

        {needsCompany && (
          <label className="block">
            <span className="text-sm font-medium text-text-primary">Issuer</span>
            <select value={company} onChange={(e) => setCompany(e.target.value)} className={FIELD_CLASS}>
              <option value="">Select the issuer</option>
              {companies.map((item) => (
                <option key={item.uuid} value={item.uuid}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        )}

        {needsCertifier && (
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-text-primary">Certificate date</span>
              <input
                type="date"
                value={certificateIssuedAt}
                onChange={(e) => setCertificateIssuedAt(e.target.value)}
                className={FIELD_CLASS}
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-text-primary">Professional body</span>
              <select value={certifierBody} onChange={(e) => setCertifierBody(e.target.value)} className={FIELD_CLASS}>
                <option value="">Select a body</option>
                {CERTIFIER_BODIES.map((body) => (
                  <option key={body.value} value={body.value}>
                    {body.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-medium text-text-primary">Accountant name</span>
              <input
                type="text"
                value={certifierName}
                onChange={(e) => setCertifierName(e.target.value)}
                className={FIELD_CLASS}
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-text-primary">Membership number</span>
              <input
                type="text"
                value={certifierMembershipNumber}
                onChange={(e) => setCertifierMembershipNumber(e.target.value)}
                className={FIELD_CLASS}
              />
            </label>
          </div>
        )}

        <label className="block">
          <span className="text-sm font-medium text-text-primary">Basis for the claim</span>
          <textarea
            value={declaredBasis}
            onChange={(e) => setDeclaredBasis(e.target.value)}
            rows={3}
            className={FIELD_CLASS}
            placeholder="Describe, in your own words, why this category applies to you"
          />
        </label>

        {!file ? (
          <div
            onDrop={handleDrop}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
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
                Drag &amp; drop or <span className="text-brand-light font-medium">browse</span>
              </p>
              <p className="text-xs text-text-muted mt-1">PDF or images, max 10 MB</p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf,image/png,image/jpeg"
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
            <button onClick={() => setFile(null)} className="text-text-muted hover:text-text-primary p-1">
              <XIcon size={16} />
            </button>
          </div>
        )}

        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={declarationAccepted}
            onChange={(e) => setDeclarationAccepted(e.target.checked)}
            className="mt-1"
          />
          <span className="text-sm text-text-secondary">
            I declare that this category applies to me and that the evidence attached is genuine.{' '}
            {WHOLESALE_ONLY_NOTICE}
          </span>
        </label>
      </div>
    </Modal>
  );
}
