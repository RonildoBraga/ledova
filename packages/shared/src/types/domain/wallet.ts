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

export interface WalletSyncResult {
  status: 'success' | 'skipped' | 'error';
  transactions?: number;
  snapshots?: number;
  holdings?: number;
  error?: string;
}

export interface SyncWalletResponse {
  success: boolean;
  wallet: Wallet;
  syncResult: WalletSyncResult;
}
