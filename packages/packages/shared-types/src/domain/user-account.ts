import type { BaseEntity } from '../common';

export interface UserAccount extends BaseEntity {
  accountNumber: string;
  accountType: string;
  activationDate: string | null;
  name: string;
  userProfile: string;
}

export type CreateUserAccount = Omit<
  UserAccount,
  'uuid' | 'createdAt' | 'updatedAt' | 'accountNumber' | 'activationDate'
>;

export type UpdateUserAccount = Partial<Omit<UserAccount, 'uuid' | 'createdAt' | 'updatedAt'>>;
