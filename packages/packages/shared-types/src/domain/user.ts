import type { KYCProvider, ReviewAnswer, VerificationStatus } from './identity-verification';

/**
 * Mirrors backend `UserProfileSerializer.Meta.fields` (camelCase via the renderer).
 * The profile endpoint does not emit `createdAt` / `updatedAt`.
 */
export interface UserProfile {
  uuid: string;
  fullName: string;
  email: string;
  isActive: boolean;
  isStaff: boolean;
  dateJoined: string;
  lastLogin: string | null;
  phoneCountryCode: string;
  phoneNumber: string;
  dateOfBirth: string | null;
  residentialAddress: string;
  citizenshipCountry: string | null;
  citizenshipCountryName: string | null;
  residenceCountry: string | null;
  residenceCountryName: string | null;
  confirmedOver18: boolean;
  confirmedAustralianResident: boolean;
  confirmedIndividualAccount: boolean;
  isIdVerified: boolean;
  termsAndConditions: boolean;
  isSignupCompleted: boolean;
  kycProvider: KYCProvider;
  verificationStatus: VerificationStatus;
  reviewResult: ReviewAnswer;
  rejectionLabels: string[] | null;
  verifiedAt: string | null;
  kycaidApplicantId: string | null;
  sumsubApplicantId: string | null;
  sumsubVerificationStatus: VerificationStatus;
}

/** Keys the serializer emits but never accepts (`read_only_fields` plus the user and country lookups). */
type UserProfileResponseOnly =
  | 'uuid'
  | 'email'
  | 'isActive'
  | 'isStaff'
  | 'dateJoined'
  | 'lastLogin'
  | 'citizenshipCountryName'
  | 'residenceCountry'
  | 'residenceCountryName'
  | 'isIdVerified'
  | 'kycProvider'
  | 'verificationStatus'
  | 'reviewResult'
  | 'rejectionLabels'
  | 'verifiedAt'
  | 'kycaidApplicantId'
  | 'sumsubApplicantId'
  | 'sumsubVerificationStatus';

export type CreateUserProfile = Omit<
  UserProfile,
  | UserProfileResponseOnly
  | 'isSignupCompleted'
  | 'termsAndConditions'
  | 'citizenshipCountry'
  | 'dateOfBirth'
  | 'confirmedOver18'
  | 'confirmedAustralianResident'
  | 'confirmedIndividualAccount'
>;

export type UpdateUserProfile = Partial<Omit<UserProfile, UserProfileResponseOnly>>;

export type CompleteUserProfile = Pick<UserProfile, 'termsAndConditions' | 'isSignupCompleted'>;

/**
 * Form data for user profile editing (signup flow and profile management).
 * Contains the editable fields users can modify directly.
 */
export interface UserProfileFormData {
  fullName: string;
  dateOfBirth: string;
  phoneCountryCode: string;
  phoneNumber: string;
  residentialAddress: string;
}
