import type { BaseEntity } from '../common';
import type { OrderingParams } from '../api';

/**
 * Nested account data returned in user preferences response.
 */
export interface SelectedAccount {
  uuid: string;
  accountNumber: string;
  accountType: string;
  activationDate: string | null;
}

/**
 * Nested portfolio data returned in user preferences response.
 */
export interface SelectedPortfolio {
  uuid: string;
  name: string;
  userAccount: string;
  isActive: boolean;
}

/**
 * User preferences with full nested objects for selected account and portfolio.
 */
export type Theme = 'dark' | 'light';
export type DisplayCurrency = 'AUD' | 'USD';

export interface UserPreferences extends BaseEntity {
  userProfile: string;
  selectedAccount: SelectedAccount | null;
  selectedPortfolio: SelectedPortfolio | null;
  theme: Theme;
  displayCurrency: DisplayCurrency;
}

export interface UserPreferencesValidationError {
  selectedAccount?: string;
  selectedPortfolio?: string;
  general?: string;
}

/**
 * Query parameters for user preferences endpoints.
 * Extends OrderingParams for sorting (single record per user, no pagination needed).
 *
 * NAMING CONVENTION: Query params use snake_case following REST API URL standards.
 */
export interface UserPreferencesQueryParams extends OrderingParams {
  userProfile?: string;
  withSelectedAccount?: boolean;
  withSelectedPortfolio?: boolean;
}

export interface UpdateUserPreferences {
  selectedAccount?: string | null;
  selectedPortfolio?: string | null;
  theme?: Theme;
  displayCurrency?: DisplayCurrency;
}

export interface UserPreferencesResponse {
  success: boolean;
  data?: UserPreferences;
  errors?: UserPreferencesValidationError;
  message?: string;
}
