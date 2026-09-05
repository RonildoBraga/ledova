import type { ReviewAnswer, UserProfile, VerificationStatus as KycStatus } from '../types';

export type VerificationStatusType = 'verified' | 'pending' | 'rejected' | 'not_started' | 'not_verified' | 'unknown';

interface VerificationStatus {
  type: VerificationStatusType;
  label: string;
}

const STATUS_LABELS: Record<VerificationStatusType, string> = {
  verified: 'Verified',
  pending: 'Pending',
  rejected: 'Rejected',
  not_started: 'Not Started',
  not_verified: 'Not Verified',
  unknown: 'Unknown',
};

const PENDING_STATUSES: ReadonlySet<string> = new Set(['pending', 'queued', 'prechecked', 'onHold']);

const REVIEW_RESULT_TYPES: Record<NonNullable<ReviewAnswer>, VerificationStatusType> = {
  GREEN: 'verified',
  YELLOW: 'pending',
  RED: 'rejected',
};

function statusOf(type: VerificationStatusType): VerificationStatus {
  return { type, label: STATUS_LABELS[type] };
}

/**
 * Maps the provider-agnostic `verificationStatus` / `reviewResult` pair the backend writes
 * (`integrations/kyc/constants.py`) to the account-status badge. A bare string is read as the
 * `verificationStatus` alone.
 */
export function getUserVerificationStatus(profile?: UserProfile | string | null): VerificationStatus {
  if (typeof profile === 'object' && profile?.isIdVerified) return statusOf('verified');

  const status: KycStatus | undefined =
    typeof profile === 'string' ? (profile as KycStatus) : profile?.verificationStatus;
  const reviewResult: ReviewAnswer = typeof profile === 'object' ? (profile?.reviewResult ?? null) : null;

  if (!status || status === 'init') return statusOf('not_started');
  if (PENDING_STATUSES.has(status)) return statusOf('pending');
  if (status === 'completed') return statusOf(reviewResult ? REVIEW_RESULT_TYPES[reviewResult] : 'unknown');
  return statusOf('unknown');
}
