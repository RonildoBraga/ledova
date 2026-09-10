import type { OrderType, OrderStatus, SwapStatus, SwapUserRole } from '../../constants';

export interface ShareToken {
  uuid: string;
  name: string;
  symbol: string;
  companyName: string;
  contractAddress: string;
  totalSupply: number;
  decimals: number;
  lastPrice?: string;
  bestBid?: string;
  bestAsk?: string;
  priceChange24h?: number;
}

export interface TransferOrder {
  uuid: string;
  token: string;
  tokenSymbol: string;
  tokenName: string;
  orderType: OrderType;
  orderTypeDisplay?: string;
  status: OrderStatus;
  statusDisplay?: string;
  walletAddress: string;
  quantity: number;
  pricePerShare: string;
  totalValue: string;
  createdAt: string;
  updatedAt?: string;
  matchedOrder?: string;
  matchedAt?: string;

  minQuantity?: number;
  filledQuantity?: number;
  remainingQuantity?: number;

  modificationCount?: number;
  lastModifiedAt?: string;
  originalQuantity?: number;
  originalPrice?: string;
}

export interface CreateOrderRequest {
  token: string;
  orderType: OrderType;
  walletUuid: string;
  walletAddress: string;
  quantity: number;
  minQuantity?: number;
  pricePerShare: string;
}

export interface OrderSubmissionRequest extends Omit<CreateOrderRequest, 'quantity' | 'minQuantity'> {
  submissionId: string;
  ownerAccountUuid: string;
  quantity: number | string;
  minQuantity?: number | string;
}

export interface OrderSubmissionSnapshot {
  submissionId: string;
  ownerAccountUuid: string;
  walletUuid: string;
  status: 'pending' | 'created' | 'refused';
  intent: {
    token: string;
    orderType: OrderType;
    walletAddress: string;
    quantity: string;
    minQuantity: string;
    pricePerShare: string;
  };
  order: TransferOrder | null;
  match: { matched: true; counterOrder: string; swapOrder: string } | null;
  refusal: { code: string; detail: string } | null;
  challenge: CreateOrderMessageResponse | null;
}

export interface OrderBookEntry {
  price: string;
  quantity: number;
  orders: number;
}

export interface OrderBook {
  token: string;
  buyOrders: OrderBookEntry[];
  sellOrders: OrderBookEntry[];
}

/* eslint-disable @typescript-eslint/naming-convention -- API query params use snake_case */
export interface GetOrdersParams {
  token?: string;
  status?: string;
  order_type?: string;
  wallet_address?: string;
}
/* eslint-enable @typescript-eslint/naming-convention */

export type WhitelistStatusState = 'whitelisted' | 'not_whitelisted' | 'unknown';

export interface WhitelistStatus {
  address: string;
  isWhitelisted: boolean;
  canReceive: boolean;
  status: WhitelistStatusState;
}

export interface WalletTokenBalance {
  token: string;
  symbol: string;
  name: string;
  balance: string;
  contractAddress: string;
  decimals?: number;
  type?: 'share_token' | 'stablecoin';
}

export interface WalletTokenBalancesResponse {
  walletAddress: string;
  balances: WalletTokenBalance[];
}

export interface MarketData {
  token: string;
  symbol: string;
  lastTrade: {
    price: string;
    shares: number;
    paymentAmount: string;
    paymentToken: string;
    completedAt: string | null;
  } | null;
  lastTradePrice: string | null;
  bestBid: string | null;
  bestAsk: string | null;
  midpointPrice: string | null;
}

export interface SwapOrder {
  uuid: string;
  status: SwapStatus;
  statusDisplay?: string;
  shareTokenSymbol: string;
  shareTokenName: string;
  shareTokenAddress?: string;
  paymentTokenSymbol: string;
  paymentTokenAddress?: string;
  sellerAddress: string;
  buyerAddress: string;
  shareAmount: number;
  paymentAmount: number;
  nonce?: number;
  orderHash?: string;
  sellerHasSigned: boolean;
  buyerHasSigned: boolean;
  isExpired?: boolean;
  isReady?: boolean;
  sellOrderUuid?: string;
  buyOrderUuid?: string;
  txHash?: string;
  expiresAt: string;
  completedAt?: string;
  errorMessage?: string;
  createdAt: string;
  updatedAt?: string;
}

export interface EIP712Domain {
  name: string;
  version: string;
  chainId: number;
  verifyingContract: string;
}

export interface EIP712TypeField {
  name: string;
  type: string;
}

/* eslint-disable @typescript-eslint/naming-convention -- EIP-712 standard requires PascalCase type names */
export interface EIP712Types {
  EIP712Domain: EIP712TypeField[];
  SwapOrder: EIP712TypeField[];
}
/* eslint-enable @typescript-eslint/naming-convention */

export interface SwapOrderMessage {
  seller: string;
  buyer: string;
  shareToken: string;
  paymentToken: string;
  shareAmount: number | string;
  paymentAmount: number | string;
  nonce: number | string;
  deadline: number | string;
}

export interface SwapTypedData {
  types: EIP712Types;
  primaryType: string;
  domain: EIP712Domain;
  message: SwapOrderMessage;
}

export interface SwapDataResponse {
  swapOrder: SwapOrder;
  typedData: SwapTypedData;
  userRole: SwapUserRole | string;
  hasSigned: boolean;
}

export interface SubmitSignatureRequest {
  signature: string;
  signerAddress: string;
}

export interface GetSwapDataParams {
  walletAddress: string;
}

export type SigningChallengePurpose = 'order_cancel' | 'order_create' | 'order_modify';

export interface SigningChallengeTypedData {
  domain: {
    name: string;
    version: string;
    chainId: number;
    verifyingContract: string;
  };
  types: Record<string, { name: string; type: string }[]>;
  message: Record<string, string | number>;
}

export interface CancelOrderMessageResponse extends SigningChallengeTypedData {
  purpose: 'order_cancel';
  orderUuid: string;
  walletAddress: string;
  digest: string;
  expiresAt: string;
}

export interface CreateOrderMessageResponse extends SigningChallengeTypedData {
  purpose: 'order_create';
  tokenUuid: string;
  walletAddress: string;
  digest: string;
  expiresAt: string;
}

export interface SignedCreateOrderRequest extends OrderSubmissionRequest {
  digest: string;
  signature: string;
}

export interface SignedCancelOrderRequest {
  digest: string;
  signature: string;
}

export interface OrderModificationRequest {
  newQuantity?: number;
  newMinQuantity?: number;
  newPricePerShare?: string;
}

export interface OrderModificationCurrentValues {
  quantity: number;
  minQuantity: number;
  pricePerShare: string;
  filledQuantity: number;
  remainingQuantity: number;
}

export interface OrderModificationNewValues {
  quantity: number;
  minQuantity: number;
  pricePerShare: string;
}

export interface OrderModificationMessageResponse extends SigningChallengeTypedData {
  purpose: 'order_modify';
  orderUuid: string;
  digest: string;
  expiresAt: string;
  currentValues: OrderModificationCurrentValues;
  newValues: OrderModificationNewValues;
}

export interface SignedOrderModificationRequest {
  digest: string;
  signature: string;
}

export interface OrderModificationChange {
  field: string;
  old: string;
  new: string;
}

export interface OrderModificationResponse {
  order: TransferOrder;
  modificationCount: number;
  changes: OrderModificationChange[];
}

export interface ShareTokenTransferTokenInfo {
  uuid: string;
  symbol: string;
  contractAddress: string;
}

export interface ShareTokenTransferTransactionData {
  to: string;
  data: string;
  value: number;
  nonce: number;
  chainId: number;
  gasPrice: number;
  gas: number;
}

export interface ShareTokenTransferPrepareResponse {
  token: ShareTokenTransferTokenInfo;
  fromAddress: string;
  toAddress: string;
  amount: number;
  transactionData: ShareTokenTransferTransactionData;
}

export interface ApprovalStatusResponse {
  swapUuid: string;
  userRole: string;
  tokenAddress: string;
  tokenSymbol: string;
  requiredAmount: number;
  currentAllowance: number;
  needsApproval: boolean;
  spender: string;
}

export interface ApprovalTransaction {
  to: string;
  from: string;
  data: string;
  value: string;
  gas: string;
  gasPrice: string;
  nonce: string;
  chainId: string;
}

export interface ApprovalDataResponse {
  needsApproval: boolean;
  swapUuid?: string;
  userRole?: string;
  transaction?: ApprovalTransaction;
  description?: string;
  tokenAddress?: string;
  tokenSymbol?: string;
  spender?: string;
  amount?: string;
  unlimited?: boolean;
  message?: string;
  currentAllowance?: number;
  requiredAmount?: number;
}
