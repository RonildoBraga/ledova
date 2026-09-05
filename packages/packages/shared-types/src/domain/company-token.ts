export type TokenStatus = 'draft' | 'deploying' | 'deployed' | 'paused';
export type TokenType = 'ordinary' | 'preference' | 'redeemable';
export type IssuanceStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type IssuanceType = 'initial' | 'additional' | 'bonus' | 'rights';
export type CapitalIncreaseStatus =
  'draft' | 'submitted' | 'under_review' | 'approved' | 'rejected' | 'executing' | 'executed' | 'failed';
export type TokenTabType = 'overview' | 'shares' | 'shareholders' | 'issuances' | 'capital-increases';

export interface CompanyShareToken {
  uuid: string;
  company: string;
  name: string;
  symbol: string;
  tokenType: TokenType;
  status: TokenStatus;
  contractAddress: string | null;
  totalSupply: string;
  decimals: number;
  isTransferable: boolean;
  isDivisible: boolean;
  deploymentTxHash: string | null;
  deployedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TokenCreate {
  /** Issuing company uuid; the backend defaults it when the caller manages exactly one company. */
  company?: string;
  name: string;
  symbol: string;
  tokenType: TokenType;
  totalSupply: string;
  decimals?: number;
  isTransferable?: boolean;
  isDivisible?: boolean;
}

export interface TokenHolder {
  address: string;
  name: string | null;
  balance: string;
  percentage: number;
  source: 'blockchain' | 'issuances';
}

export interface TokenHoldersResponse {
  token: {
    uuid: string;
    name: string;
    symbol: string;
    status: TokenStatus;
    totalSupply: string;
  };
  holders: TokenHolder[];
  totalHolders: number;
}

export interface TokenIssuance {
  uuid: string;
  token: string;
  tokenSymbol: string;
  recipientAddress: string;
  recipientName: string;
  amount: string;
  issuanceType: IssuanceType;
  issuanceTypeDisplay: string;
  reason: string;
  status: IssuanceStatus;
  statusDisplay: string;
  txHash: string | null;
  blockNumber: number | null;
  initiatedBy: string | null;
  initiatedByEmail: string | null;
  processedAt: string | null;
  completedAt: string | null;
  createdAt: string;
}

export interface TokenIssuancesResponse {
  results: TokenIssuance[];
  count: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface CapitalIncreaseRequest {
  uuid: string;
  token: string;
  tokenSymbol: string;
  tokenName: string;
  additionalShares: number;
  newAuthorizedTotal: number;
  purpose: string;
  boardResolutionReference: string;
  shareholderApprovalReference?: string;
  status: CapitalIncreaseStatus;
  statusDisplay: string;
  dilutionPercentage: number | null;
  submittedBy: string | null;
  submittedByEmail: string | null;
  submittedAt: string | null;
  reviewedBy?: string | null;
  reviewedByEmail?: string | null;
  reviewedAt?: string | null;
  reviewNotes?: string;
  rejectionReason?: string;
  executedIssuance?: string | null;
  executedAt?: string | null;
  canBeEdited?: boolean;
  canBeSubmitted?: boolean;
  createdAt: string;
  updatedAt?: string;
}

export interface CapitalIncreaseCreate {
  token: string;
  additionalShares: number;
  newAuthorizedTotal: number;
  purpose: string;
  boardResolutionReference: string;
  shareholderApprovalReference?: string;
}

export interface CapitalIncreaseResponse {
  results: CapitalIncreaseRequest[];
  count: number;
  page?: number;
  pageSize?: number;
}
