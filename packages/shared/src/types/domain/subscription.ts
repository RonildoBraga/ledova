import type { SettlementRail, SubscriptionStatus } from '../../constants';

export interface PaymentInstruction {
  rail: SettlementRail;
  railDisplay: string;
  reference: string;
  amountDue: string;
  currency: string;
  paymentDueAt: string | null;
  issuedAt: string | null;
  payee: string;
  bankAccountName?: string;
  bankBsb?: string;
  bankAccountNumber?: string;
  receivingWalletAddress?: string;
  chain?: string;
  assetSymbol?: string;
  contractAddress?: string;
  decimals?: number;
  settlementAmount?: string;
}

export interface Subscription {
  uuid: string;
  offeringUuid: string;
  tokenSymbol: string;
  tokenName: string;
  companyName: string;
  status: SubscriptionStatus;
  statusDisplay: string;
  quantity: number;
  allottedQuantity: number | null;
  pricePerShare: string;
  amountDue: string;
  amountReceived: string | null;
  settlementRail: SettlementRail;
  settlementRailDisplay: string;
  reference: string;
  paymentDueAt: string | null;
  walletAddress: string;
  createdAt: string;
}

export interface SubscriptionDetail extends Subscription {
  settlementAssetSymbol: string | null;
  settlementAmount: number | null;
  amountOutstanding: string;
  paymentInstruction: PaymentInstruction | null;
  paymentInstructionIssuedAt: string | null;
  paymentReceivedOn: string | null;
  paymentReferenceSeen: string;
  paymentTxHash: string;
  paymentNotes: string;
  refundAmount: string | null;
  refundedAt: string | null;
  refundReference: string;
  updatedAt: string;
}

export interface IssuerSubscription {
  uuid: string;
  status: SubscriptionStatus;
  statusDisplay: string;
  investorName: string;
  quantity: number;
  allottedQuantity: number | null;
  pricePerShare: string;
  amountDue: string;
  amountReceived: string | null;
  settlementRailDisplay: string;
  reference: string;
  paymentDueAt: string | null;
  paymentConfirmedAt: string | null;
  allotmentState: string;
  walletAddress: string;
  createdAt: string;
}

export interface SubscriptionInput {
  offering: string;
  userAccount: string;
  wallet: string;
  quantity: number;
}
