import type { BaseEntity } from '../common';
import type { BaseQueryParams } from '../api';

export type WalletType = 'hardware' | 'software';

export interface Wallet extends BaseEntity {
  userAccount: string;
  name?: string;
  address: string;
  chain: string;
  walletType?: WalletType;
  verificationStatus: 'PENDING' | 'VERIFIED';
  verificationChallenge?: string;
  verificationSignature?: string;
  verifiedAt?: string;
  nativeBalance: string;
  nativeMarketValue: string;
  marketValue: string;
  lastSyncedAt?: string;
  derivationPath?: string;
  masterFingerprint?: string;
  addressIndex?: number;
  parentPublicKey?: string;
  parentChainCode?: string;
  parentDerivationPath?: string;
}

export interface WalletQueryParams extends BaseQueryParams {
  user_account?: string;
  chain?: string;
  verification_status?: 'PENDING' | 'VERIFIED';
}

export type CreateWallet = {
  userAccount: string;
  name?: string;
  address: string;
  chain: string;
  walletType?: WalletType;
  derivationPath?: string;
  masterFingerprint?: string;
  addressIndex?: number;
  parentPublicKey?: string;
  parentChainCode?: string;
  parentDerivationPath?: string;
};

export interface SyncBalanceResponse {
  success: boolean;
  balance?: string;
  chain?: string;
  lastSyncedAt?: string;
  message?: string;
}

export interface SyncWalletResponse {
  success: boolean;
  message: string;
  taskId: string;
  wallet: Wallet;
}
