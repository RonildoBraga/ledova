/**
 * Types for the backend `documents` app (POST/GET /api/v1/documents/).
 *
 * Mirror of:
 *   backend/documents/serializers/document.py
 *   backend/documents/schemas/payslip.py
 *
 * Kept local to the dashboard for the PoC. Lift into
 * @ledova/shared-types when mobile needs it too.
 */

export type DocumentType = 'payslip' | 'bank_statement' | 'tax_return' | 'other';

export type ExtractionStatus = 'pending' | 'running' | 'succeeded' | 'failed';

/**
 * The shape Qwen2.5-VL-7B returns for a payslip, validated by the
 * backend pydantic schema. Decimals come over the wire as strings —
 * we keep them as strings until they reach a formatter.
 *
 * Keys are camelCase because DRF's camelcase renderer converts even
 * JSONField values on output. The backend stores them snake_case but
 * the wire format is what we type to.
 */
export interface PayslipExtraction {
  employeeName: string | null;
  employerName: string | null;
  abn: string | null;
  periodStart: string | null; // YYYY-MM-DD
  periodEnd: string | null;
  payDate: string | null;
  grossPay: string | null;
  netPay: string | null;
  taxWithheld: string | null;
  superannuation: string | null;
  ytdGross: string | null;
  ytdTax: string | null;
  confidence: number;
  extractionWarnings: string[];
}

export interface DocumentExtraction {
  uuid: string;
  status: ExtractionStatus;
  modelName: string;
  parsedJson: PayslipExtraction | null;
  confidence: number | null;
  warnings: string[];
  error: string;
  durationMs: number | null;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Document {
  uuid: string;
  documentType: DocumentType;
  originalFilename: string;
  mimeType: string;
  note: string;
  latestExtraction: DocumentExtraction | null;
  createdAt: string;
  updatedAt: string;
}
