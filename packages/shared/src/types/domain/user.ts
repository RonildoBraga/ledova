import type { KYCProvider, ReviewAnswer, VerificationStatus } from './identity-verification';

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

export type UpdateUserProfile = Partial<Omit<UserProfile, UserProfileResponseOnly>>;

export type CompleteUserProfile = Pick<UserProfile, 'termsAndConditions' | 'isSignupCompleted'>;

export interface UserProfileFormData {
  fullName: string;
  dateOfBirth: string;
  phoneCountryCode: string;
  phoneNumber: string;
  residentialAddress: string;
}
