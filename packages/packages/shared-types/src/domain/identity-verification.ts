export type KYCProvider = 'sumsub' | 'kycaid';

export type VerificationStatus = 'init' | 'pending' | 'queued' | 'completed' | 'onHold' | null;

export type ReviewAnswer = 'GREEN' | 'RED' | 'YELLOW' | null;

export interface IdentityVerificationToken {
  provider: KYCProvider;
  accessToken: string | null;
  applicantId: string | null;
  formUrl: string | null;
}

export interface ExtractedApplicantData {
  fullName: string | null;
  dateOfBirth: string | null;
  address: string | null;
}

export interface IdentityVerificationStatus {
  provider: KYCProvider;
  applicantId: string | null;
  status: VerificationStatus;
  reviewResult: string | null;
  reviewAnswer: ReviewAnswer;
  isVerified: boolean;
  verifiedAt: string | null;
  rejectionLabels: string[];
  needsRetry: boolean;
  extractedData: ExtractedApplicantData | null;
}
