import type { BaseEntity } from '../common';

export type CompanyStatus =
  | 'draft'
  | 'submitted'
  | 'review'
  | 'info_required'
  | 'approved'
  | 'active'
  | 'warning'
  | 'suspended'
  | 'delisted'
  | 'rejected'
  | 'withdrawn';

export type CompanyType = 'pty' | 'public' | 'unlisted';

export type DocumentType =
  | 'cert_inc'
  | 'asic'
  | 'constitution'
  | 'share_register'
  | 'financials'
  | 'auditor_report'
  | 'director_id'
  | 'beneficial_ownership'
  | 'shareholder'
  | 'business_plan'
  | 'risk_disclosure'
  | 'prospectus'
  | 'legal_opinion'
  | 'tax_return'
  | 'bank_statement'
  | 'other';

export interface CompanyDocument {
  uuid: string;
  documentType: DocumentType;
  documentTypeDisplay: string;
  name: string;
  fileUrl: string;
  fileSize: number;
  mimeType: string;
  isVerified: boolean;
  verifiedAt: string | null;
  createdAt: string;
}

export interface CompanyUserProfile {
  uuid: string;
  firstName: string;
  lastName: string;
  fullName: string;
  email: string;
  phone: string | null;
}

export interface Company extends BaseEntity {
  name: string;
  tradingName: string;
  displayName: string;
  companyType: CompanyType;
  companyTypeDisplay: string;
  acn: string;
  abn: string;
  status: CompanyStatus;
  statusDisplay: string;
  email: string;
  phone: string;
  addressLine1: string;
  addressLine2: string;
  city: string;
  state: string;
  postcode: string;
  country: string;

  submittedAt: string | null;
  reviewStartedAt: string | null;
  approvedAt: string | null;
  activatedAt: string | null;
  infoRequestedAt: string | null;
  infoRequestReason: string;

  additionalInfoResponse: string;
  rejectionAt: string | null;
  rejectionReason: string;
  withdrawnAt: string | null;
  withdrawalReason: string;

  operatorAddress: string;
  description: string;
  industry: string;
  foundedYear: number | null;
  isActive: boolean;
  isApproved: boolean;
  isPendingReview: boolean;
  canIssueTokens: boolean;
  primaryContact: CompanyUserProfile | null;
  documents: CompanyDocument[];
}

export interface CompanyUpdate {
  name?: string;
  tradingName?: string;
  companyType?: CompanyType;
  acn?: string;
  abn?: string;
  addressLine1?: string;
  addressLine2?: string;
  city?: string;
  state?: string;
  postcode?: string;
  phone?: string;
  description?: string;
}

export interface CompanyStats {
  totalTokens: number;
  totalShareholders: number;
  pendingActions: number;
}

export interface CompanyRegistration {
  name: string;
  tradingName?: string;
  companyType: CompanyType;
  acn: string;
  abn?: string;
  primaryContact: {
    firstName: string;
    lastName: string;
    phone?: string;
  };
}

export interface CompanyRegistrationResponse {
  message: string;
  company: Company;
}

export interface ApplicationStatus {
  uuid: string;
  status: CompanyStatus;
  statusDisplay: string;
  submittedAt: string | null;
  reviewStartedAt: string | null;
  reviewCompletedAt: string | null;
  approvedAt: string | null;
  infoRequestedAt: string | null;
  infoRequestReason: string;
  rejectionAt: string | null;
  rejectionReason: string;
  withdrawnAt: string | null;
  withdrawalReason: string;
}

export interface ApplicationResponse {
  message: string;
  company: ApplicationStatus;
}

export interface ApplicationResubmit {
  response: string;
}

export interface ApplicationWithdraw {
  reason?: string;
}

export interface DocumentUpload {
  documentType: DocumentType;
  name: string;
  file: File;
}
