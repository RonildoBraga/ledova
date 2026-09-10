import type { JsonValue } from '../common';

export interface FinancialProfile {
  uuid: string;
  userProfile: string;
  occupation: string | null;
  sourceOfFunds: JsonValue;
  sourceOfFundsOtherText: string | null;
  intendedUse: string | null;
  intendedUseOtherText: string | null;
}

export type CreateFinancialProfile = Omit<FinancialProfile, 'uuid' | 'userProfile'>;

export type UpdateFinancialProfile = Partial<CreateFinancialProfile>;
