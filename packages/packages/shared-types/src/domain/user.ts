import type { BaseEntity } from '../common';

export interface UserProfile extends BaseEntity {
  citizenshipCountry: string | null;
  citizenshipCountryName: string | null;
  fullName: string;
  email: string;
  isActive: boolean;
  isStaff: boolean;
  dateJoined: string;
  lastLogin: string | null;
  dateOfBirth: string | null;
  residentialAddress: string;
  phoneCountryCode: string;
  phoneNumber: string;
  confirmedOver18: boolean;
  confirmedAustralianResident: boolean;
  confirmedIndividualAccount: boolean;
  preScreeningCompletedAt: string | null;
  isIdVerified: boolean;
  termsAndConditions: boolean;
  isSignupCompleted: boolean;
  sumsubApplicantId: string | null;
  sumsubVerificationStatus: string | null;
  sumsubReviewResult: string | null;
  sumsubReviewAnswer: string | null;
  sumsubRejectionLabels: string[];
  sumsubVerifiedAt: string | null;
}

export type CreateUserProfile = Omit<
  UserProfile,
  | 'uuid'
  | 'createdAt'
  | 'updatedAt'
  | 'email'
  | 'isActive'
  | 'isStaff'
  | 'dateJoined'
  | 'lastLogin'
  | 'isIdVerified'
  | 'isSignupCompleted'
  | 'termsAndConditions'
  | 'citizenshipCountry'
  | 'dateOfBirth'
  | 'confirmedOver18'
  | 'confirmedAustralianResident'
  | 'confirmedIndividualAccount'
  | 'preScreeningCompletedAt'
>;

export type UpdateUserProfile = Partial<
  Omit<
    UserProfile,
    | 'uuid'
    | 'createdAt'
    | 'updatedAt'
    | 'email'
    | 'isActive'
    | 'isStaff'
    | 'dateJoined'
    | 'lastLogin'
    | 'citizenshipCountryName'
    | 'isIdVerified'
    | 'preScreeningCompletedAt'
    | 'sumsubApplicantId'
    | 'sumsubVerificationStatus'
    | 'sumsubReviewResult'
    | 'sumsubReviewAnswer'
    | 'sumsubRejectionLabels'
    | 'sumsubVerifiedAt'
  >
>;

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
