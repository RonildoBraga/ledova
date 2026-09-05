export type DocumentType = 'payslip' | 'bank_statement' | 'tax_return' | 'other';

export type ExtractionStatus = 'pending' | 'running' | 'succeeded' | 'failed';

export interface PayslipExtraction {
  employeeName: string | null;
  employerName: string | null;
  abn: string | null;
  periodStart: string | null;
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
