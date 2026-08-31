import type { BaseEntity } from '../common';
import type { BaseQueryParams, DateRangeParams } from '../api';

export interface Transaction extends BaseEntity {
  txHash: string;
  chain: string;
  fromAddress: string;
  toAddress: string | null;
  asset: string;
  assetSymbol?: string;
  assetName?: string;
  amount: string;
  marketValue?: string | null;
  blockTimestamp: string;
  blockNumber?: number;
  status?: string;
  transactionFeeEstimated?: string;
  transactionFee?: string;
  wallet: string;
  walletAddress?: string;

  orderType?: 'BUY' | 'SELL' | 'ISSUANCE' | 'MINT' | 'PAYMENT_SENT' | 'PAYMENT_RECEIVED';
  pricePerShare?: string;
  paymentToken?: string;
  transactionType?: string;
  issuanceType?: string;
}

export interface TransactionQueryParams extends BaseQueryParams, DateRangeParams {
  wallet?: string;
  chain?: string;
  asset?: string;
  direction?: 'incoming' | 'outgoing';
  min_amount?: number;
  max_amount?: number;
}
