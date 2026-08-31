import type * as React from 'react';
import type { UserProfile, FinancialProfile, AssetQueryParams } from './domain';
import type { FieldValidation, FormValidation } from './validation';

export type { CountryData } from '@ledova/shared-constants';
export type { AssetQueryParams };

export interface ReviewData {
  userProfile: UserProfile | null;
  financialProfile: FinancialProfile | null;
}

export interface UserProfileFormValidation extends FormValidation {
  fullName: FieldValidation;
  residentialAddress: FieldValidation;
  phoneNumber: FieldValidation;
}

export interface FinancialProfileFormState {
  userProfileId: string;
  occupation: string;
  sourceOfFunds: string[];
  sourceOfFundsOtherText: string;
  intendedUse: string;
  intendedUseOtherText: string;
}

export interface PasswordValidation {
  isValid: boolean;
  lengthValid: boolean;
  notNumeric: boolean;
}

export interface EmailConfirmationValidation {
  isValid: boolean;
  isEmpty: boolean;
  isValidFormat: boolean;
}

export interface ChartDataPoint {
  dayIndex: number;
  date: string;
  price: number;
  changePercent: number;
}

export interface RadioGroupFieldProps {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  error?: string[];
  onChange: (value: string) => void;
}

export interface CheckboxGroupFieldProps {
  label: string;
  value: string[];
  options: Array<{ value: string; label: string }>;
  error?: string[];
  onChange: (values: string[]) => void;
}

export interface LayoutProps {
  children: React.ReactNode;
}

export interface LoadingStateProps {
  message?: string;
  className?: string;
}

export interface ErrorStateProps {
  title?: string;
  message?: string;
  retryLabel?: string;
  onRetry: () => void;
  className?: string;
}
