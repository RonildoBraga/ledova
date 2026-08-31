import type { UserProfile } from '@ledova/shared-types';

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

export function getUserVerificationStatus(profile?: UserProfile | string | null): VerificationStatus {
  // If the profile object has isIdVerified set, that's the definitive answer
  if (typeof profile === 'object' && profile?.isIdVerified) {
    return { type: 'verified', label: STATUS_LABELS.verified };
  }

  const status = typeof profile === 'string' ? profile : profile?.sumsubVerificationStatus;
  if (!status) return { type: 'not_started', label: STATUS_LABELS.not_started };
  const normalized = status.toLowerCase();
  if (normalized === 'verified' || normalized === 'approved')
    return { type: 'verified', label: STATUS_LABELS.verified };
  if (normalized === 'pending' || normalized === 'in_progress')
    return { type: 'pending', label: STATUS_LABELS.pending };
  if (normalized === 'rejected' || normalized === 'failed') return { type: 'rejected', label: STATUS_LABELS.rejected };
  if (normalized === 'not_verified') return { type: 'not_verified', label: STATUS_LABELS.not_verified };
  return { type: 'unknown', label: STATUS_LABELS.unknown };
}
