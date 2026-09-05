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
  // Partial fill support
  minQuantity?: number;
  filledQuantity?: number;
  remainingQuantity?: number;
  // Modification tracking
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

export interface BroadcastResponse {
  txHash: string;
  status: string;
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

export interface WhitelistStatus {
  address: string;
  isWhitelisted: boolean;
  investorType: number;
  investorTypeDisplay: string;
  kycTimestamp: number;
  canReceive: boolean;
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
  tokenUuid: string;
  lastPrice: string;
  priceChange24h: number;
  volume24h: string;
  high24h: string;
  low24h: string;
  openOrders: number;
  totalTrades: number;
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

export interface CreateOrderMessageResponse {
  walletAddress: string;
  tokenUuid: string;
  orderType: string;
  quantity: number;
  pricePerShare: string;
  message: string;
  instructions: string;
}

export interface CancelOrderMessageResponse {
  orderUuid: string;
  walletAddress: string;
  message: string;
  instructions: string;
}

export interface SignedCreateOrderRequest extends CreateOrderRequest {
  message: string;
  signature: string;
}

export interface SignedCancelOrderRequest {
  message: string;
  signature: string;
}

// ============================================================================
// Order Modification Types
// ============================================================================

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

export interface OrderModificationMessageResponse {
  message: string;
  messageHash: string;
  orderUuid: string;
  nonce: number;
  currentValues: OrderModificationCurrentValues;
  newValues: OrderModificationNewValues;
}

export interface SignedOrderModificationRequest {
  message: string;
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

// ============================================================================
// Direct Share Token Transfer Types
// ============================================================================

/**
 * Token info included in transfer prepare response.
 */
export interface ShareTokenTransferTokenInfo {
  uuid: string;
  symbol: string;
  name: string;
  contractAddress: string;
}

/**
 * Transaction data for signing a share token transfer.
 */
export interface ShareTokenTransferTransactionData {
  to: string;
  data: string;
  value: number;
  nonce: number;
  chainId: number;
  gasPrice: number;
  gas: number;
}

/**
 * Response from prepare share token transfer endpoint.
 */
export interface ShareTokenTransferPrepareResponse {
  token: ShareTokenTransferTokenInfo;
  fromAddress: string;
  toAddress: string;
  amount: number;
  transactionData: ShareTokenTransferTransactionData;
}

// ============================================================================
// Swap Approval Types
// ============================================================================

/**
 * Response from swap approval status endpoint.
 * Indicates whether the user needs to approve token spending.
 */
export interface ApprovalStatusResponse {
  swapUuid: string;
  userRole: string;
  tokenAddress: string;
  tokenSymbol: string;
  requiredAmount: string;
  currentAllowance: string;
  needsApproval: boolean;
  spender: string;
}

/**
 * Transaction data for token approval.
 */
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

/**
 * Response from swap approval data endpoint.
 * Contains transaction data for signing if approval is needed.
 */
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
  currentAllowance?: string;
  requiredAmount?: string;
}
