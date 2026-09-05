import type { BaseEntity } from '../common';

export type InvestorCategory =
  'product_value' | 'accountant_certificate' | 'professional_investor' | 'associated_person';

export type InvestorClassificationStatus = 'submitted' | 'verified' | 'rejected' | 'revoked';

export type CertifierBody = 'ca_anz' | 'cpa_australia' | 'ipa';

export type InvestorEligibilityReason =
  | 'no_investor_account'
  | 'account_not_in_good_standing'
  | 'identity_not_verified'
  | 'no_live_classification'
  | 'amount_below_product_value_threshold';

export interface InvestorClassification extends Pick<BaseEntity, 'uuid' | 'createdAt'> {
  userAccount: string;
  company: string | null;
  category: InvestorCategory;
  categoryDisplay: string;
  status: InvestorClassificationStatus;
  statusDisplay: string;
  declarationAccepted: boolean;
  declarationText: string;
  declaredBasis: string;
  evidenceUrl: string | null;
  evidenceFileSize: number | null;
  evidenceMimeType: string;
  certificateIssuedAt: string | null;
  certifierName: string;
  certifierBody: CertifierBody | '';
  certifierMembershipNumber: string;
  submittedAt: string | null;
  reviewedAt: string | null;
  reviewNotes: string;
  rejectionReason: string;
  expiresAt: string | null;
  isLive: boolean;
  isExpired: boolean;
}

export interface InvestorEligibility {
  isEligible: boolean;
  reasons: InvestorEligibilityReason[];
  account: string | null;
  classification: InvestorClassification | null;
}

export interface InvestorClassificationSubmission {
  userAccount: string;
  category: InvestorCategory;
  declaredBasis: string;
  file: File;
  company?: string;
  certificateIssuedAt?: string;
  certifierName?: string;
  certifierBody?: CertifierBody;
  certifierMembershipNumber?: string;
}
