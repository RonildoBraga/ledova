import type { BaseEntity } from '../common';

export interface SelectedAccount {
  uuid: string;
  accountNumber: string;
  accountType: string;
  activationDate: string | null;
}

export interface SelectedPortfolio {
  uuid: string;
  name: string;
  userAccount: string;
  isActive: boolean;
}

export type Theme = 'dark' | 'light';
export type DisplayCurrency = 'AUD' | 'USD';

export interface UserPreferences extends BaseEntity {
  userProfile: string;
  selectedAccount: SelectedAccount | null;
  selectedPortfolio: SelectedPortfolio | null;
  theme: Theme;
  displayCurrency: DisplayCurrency;
}

export interface UpdateUserPreferences {
  selectedAccount?: string | null;
  selectedPortfolio?: string | null;
  theme?: Theme;
  displayCurrency?: DisplayCurrency;
}
