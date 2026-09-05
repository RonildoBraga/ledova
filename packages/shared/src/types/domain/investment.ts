import type { BaseEntity } from '../common';

export interface FinancialProfile extends BaseEntity {
  userProfile: string;
  occupation: string | null;
  sourceOfFunds: string[];
  sourceOfFundsOtherText: string | null;
  intendedUse: string | null;
  intendedUseOtherText: string | null;
}

export type CreateFinancialProfile = Omit<FinancialProfile, 'uuid' | 'createdAt' | 'updatedAt' | 'userProfile'>;

export type UpdateFinancialProfile = Partial<
  Omit<FinancialProfile, 'uuid' | 'createdAt' | 'updatedAt' | 'userProfile'>
>;
