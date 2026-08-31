/**
 * Reusable upload + extraction-status panel.
 *
 * Drop on /user-profile (current home) or on a future /documents page
 * unchanged — it owns its own data fetching and queueing.
 *
 * Designed for payslips. Extending to bank statements / tax returns
 * is mostly adding more types to DOCUMENT_TYPE_LABELS and giving the
 * result card a per-type field renderer.
 */

import { useRef, useState } from 'react';
import {
  CloudArrowUpIcon,
  FileTextIcon,
  CheckCircleIcon,
  WarningIcon,
  XCircleIcon,
  ClockIcon,
  TrashIcon,
} from '@phosphor-icons/react';

import { DESIGN_TOKENS } from '@ledova/shared-constants';

import { useDeleteDocument, useDocument, useDocuments, useUploadDocument } from '@hooks/useDocuments';
import type { Document, DocumentType, ExtractionStatus, PayslipExtraction } from '../../types/document';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  payslip: 'Payslip',
  bank_statement: 'Bank statement',
  tax_return: 'Tax return',
  other: 'Other',
};

const MAX_FILE_MB = 10;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatMoney(raw: string | null): string {
  if (!raw) return '—';
  const n = Number(raw);
  if (Number.isNaN(n)) return raw;
  return n.toLocaleString(undefined, { style: 'currency', currency: 'AUD', maximumFractionDigits: 2 });
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' });
}

// ---------------------------------------------------------------------------
// Status pill
// ---------------------------------------------------------------------------

function StatusPill({ status }: { status: ExtractionStatus | undefined }) {
  if (!status || status === 'pending') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-surface-hover text-xs text-text-muted">
        <ClockIcon size={ICON_SM} /> Queued
      </span>
    );
  }
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-brand-light/10 text-xs text-brand-light">
        <ClockIcon size={ICON_SM} weight="bold" /> Extracting…
      </span>
    );
  }
  if (status === 'succeeded') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-500/10 text-xs text-emerald-400">
        <CheckCircleIcon size={ICON_SM} weight="fill" /> Extracted
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-red-500/10 text-xs text-red-400">
      <XCircleIcon size={ICON_SM} weight="fill" /> Failed
    </span>
  );
}

// ---------------------------------------------------------------------------
// Payslip result fields
// ---------------------------------------------------------------------------

function PayslipResult({ data, durationMs }: { data: PayslipExtraction; durationMs: number | null }) {
  const fields: { label: string; value: string }[] = [
    { label: 'Employee', value: data.employeeName ?? '—' },
    { label: 'Employer', value: data.employerName ?? '—' },
    { label: 'ABN', value: data.abn ?? '—' },
    { label: 'Pay period', value: `${formatDate(data.periodStart)} → ${formatDate(data.periodEnd)}` },
    { label: 'Gross pay', value: formatMoney(data.grossPay) },
    { label: 'Net pay', value: formatMoney(data.netPay) },
    { label: 'Tax withheld', value: formatMoney(data.taxWithheld) },
    { label: 'Superannuation', value: formatMoney(data.superannuation) },
    { label: 'YTD gross', value: formatMoney(data.ytdGross) },
    { label: 'YTD tax', value: formatMoney(data.ytdTax) },
  ];

  return (
    <div className="mt-3 space-y-2">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {fields.map((f) => (
          <div key={f.label} className="flex justify-between items-baseline text-sm gap-2 min-w-0">
            <span className="text-text-muted">{f.label}</span>
            <span className="text-text-primary text-right truncate">{f.value}</span>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between pt-2 mt-2 border-t border-border-subtle text-xs text-text-muted">
        <span>Confidence: {(data.confidence * 100).toFixed(0)}%</span>
        {durationMs != null && <span>Extracted in {(durationMs / 1000).toFixed(1)}s</span>}
      </div>

      {data.extractionWarnings && data.extractionWarnings.length > 0 && (
        <div className="mt-2 flex items-start gap-2 text-xs text-amber-400">
          <WarningIcon size={ICON_SM} weight="bold" className="mt-0.5 flex-shrink-0" />
          <span>{data.extractionWarnings.join(' · ')}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single document card (live-polled if still running)
// ---------------------------------------------------------------------------

function DocumentCard({ initialDoc }: { initialDoc: Document }) {
  // Polls every 3s while pending/running, stops once succeeded/failed.
  const liveQuery = useDocument(initialDoc.uuid);
  const doc = liveQuery.data ?? initialDoc;
  const extraction = doc.latestExtraction;
  const del = useDeleteDocument();

  const handleDelete = () => {
    if (!window.confirm(`Delete "${doc.originalFilename}"? This cannot be undone.`)) return;
    del.mutate(doc.uuid);
  };

  return (
    <div className="border border-border-subtle rounded-lg p-3 bg-surface-tertiary/50">
      <div className="flex items-center gap-3">
        <FileTextIcon size={ICON_MD} className="text-text-muted flex-shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-text-primary truncate">{doc.originalFilename}</p>
          <p className="text-xs text-text-muted">
            {DOCUMENT_TYPE_LABELS[doc.documentType]} · {formatDate(doc.createdAt)}
          </p>
        </div>
        <StatusPill status={extraction?.status} />
        <button
          type="button"
          onClick={handleDelete}
          disabled={del.isPending}
          title="Delete document"
          className="p-1.5 text-text-muted hover:text-red-400 transition-colors disabled:opacity-50 flex-shrink-0"
        >
          <TrashIcon size={ICON_SM} weight="regular" />
        </button>
      </div>

      {extraction?.status === 'succeeded' && extraction.parsedJson && (
        <PayslipResult data={extraction.parsedJson as PayslipExtraction} durationMs={extraction.durationMs} />
      )}

      {extraction?.status === 'failed' && extraction.error && (
        <div className="mt-3 text-xs text-red-400 bg-red-500/10 rounded p-2">{extraction.error}</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Upload card (drag-and-drop + click)
// ---------------------------------------------------------------------------

function UploadCard() {
  const [file, setFile] = useState<File | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>('payslip');
  const [note, setNote] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const upload = useUploadDocument();

  const handleSubmit = async () => {
    if (!file) return;
    if (file.size > MAX_FILE_MB * 1024 * 1024) {
      alert(`File too large. Max ${MAX_FILE_MB} MB.`);
      return;
    }
    await upload.mutateAsync({ file, documentType, note });
    // Reset for the next upload.
    setFile(null);
    setNote('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="border border-dashed border-border-default rounded-lg p-4 space-y-3">
      {!file ? (
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="w-full flex flex-col items-center justify-center py-6 text-text-muted hover:text-text-primary transition"
        >
          <CloudArrowUpIcon size={32} className="mb-2" />
          <p className="text-sm">Click to upload a payslip</p>
          <p className="text-xs mt-1">PDF or image, max {MAX_FILE_MB} MB</p>
        </button>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-3 p-3 rounded-lg bg-surface-hover">
            <FileTextIcon size={ICON_MD} className="text-brand-light flex-shrink-0" weight="regular" />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-text-primary truncate">{file.name}</p>
              <p className="text-xs text-text-muted">{formatFileSize(file.size)}</p>
            </div>
            <button
              type="button"
              onClick={() => setFile(null)}
              className="text-text-muted hover:text-text-primary p-1 flex-shrink-0"
              disabled={upload.isPending}
            >
              <XCircleIcon size={20} />
            </button>
          </div>

          <div className="flex gap-2">
            <select
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value as DocumentType)}
              className="bg-surface-secondary border border-border-subtle rounded px-3 py-2 text-sm text-text-primary"
              disabled={upload.isPending}
            >
              <option value="payslip">Payslip</option>
              <option value="bank_statement" disabled>
                Bank statement (coming soon)
              </option>
              <option value="tax_return" disabled>
                Tax return (coming soon)
              </option>
            </select>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Note (optional)"
              maxLength={255}
              className="flex-1 bg-surface-secondary border border-border-subtle rounded px-3 py-2 text-sm text-text-primary placeholder:text-text-muted"
              disabled={upload.isPending}
            />
          </div>

          <button
            type="button"
            onClick={handleSubmit}
            disabled={upload.isPending}
            className="w-full px-4 py-2 rounded bg-brand text-white hover:bg-brand-dark text-sm font-medium disabled:opacity-50"
          >
            {upload.isPending ? 'Uploading…' : 'Upload & extract'}
          </button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,image/png,image/jpeg,image/jpg"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="hidden"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function DocumentsPanel() {
  const docs = useDocuments();
  const list = docs.data?.results ?? [];

  return (
    <div className="space-y-3">
      <UploadCard />

      {docs.isLoading && <p className="text-sm text-text-muted">Loading…</p>}

      {!docs.isLoading && list.length === 0 && (
        <p className="text-sm text-text-muted">No documents yet — upload your first payslip above.</p>
      )}

      {list.map((doc) => (
        <DocumentCard key={doc.uuid} initialDoc={doc} />
      ))}
    </div>
  );
}
