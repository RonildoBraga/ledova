import { AxiosInstance } from 'axios';
import { TRADING_ENDPOINTS } from '../constants';
import type {
  ShareToken,
  TransferOrder,
  CreateOrderRequest,
  OrderBook,
  GetOrdersParams,
  WhitelistStatus,
  SwapOrder,
  SwapDataResponse,
  SubmitSignatureRequest,
  GetSwapDataParams,
  CreateOrderMessageResponse,
  CancelOrderMessageResponse,
  SignedCreateOrderRequest,
  SignedCancelOrderRequest,
  WalletTokenBalancesResponse,
  MarketData,
  PaginatedResponse,
  OrderModificationRequest,
  OrderModificationMessageResponse,
  SignedOrderModificationRequest,
  OrderModificationResponse,
  ApprovalStatusResponse,
  ApprovalDataResponse,
} from '../types';

export const getShareTokens = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<ShareToken>>(TRADING_ENDPOINTS.TOKENS.LIST);

export const getOrderBook = (apiClient: AxiosInstance, tokenUuid: string) =>
  apiClient.get<OrderBook>(TRADING_ENDPOINTS.TOKENS.ORDER_BOOK(tokenUuid));

export const getMarketData = (apiClient: AxiosInstance, tokenUuid: string) =>
  apiClient.get<MarketData>(TRADING_ENDPOINTS.TOKENS.MARKET_DATA(tokenUuid));

export const getOrders = (apiClient: AxiosInstance, params?: GetOrdersParams) =>
  apiClient.get<PaginatedResponse<TransferOrder>>(TRADING_ENDPOINTS.ORDERS.LIST, { params });

export const getUserOrders = (apiClient: AxiosInstance, walletAddress: string) =>
  apiClient.get<PaginatedResponse<TransferOrder>>(TRADING_ENDPOINTS.ORDERS.LIST, {
    params: { wallet_address: walletAddress },
  });

export const getOrderCreateMessage = (apiClient: AxiosInstance, data: CreateOrderRequest) =>
  apiClient.post<CreateOrderMessageResponse>(TRADING_ENDPOINTS.ORDERS.CREATE_MESSAGE, {
    token: data.token,
    order_type: data.orderType.toLowerCase(),
    wallet_uuid: data.walletUuid,
    wallet_address: data.walletAddress,
    quantity: data.quantity,
    min_quantity: data.minQuantity ?? 0,
    price_per_share: data.pricePerShare,
  });

export const getOrderCancelMessage = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<CancelOrderMessageResponse>(TRADING_ENDPOINTS.ORDERS.CANCEL_MESSAGE(uuid));

export const createOrder = (apiClient: AxiosInstance, data: SignedCreateOrderRequest) =>
  apiClient.post<TransferOrder>(TRADING_ENDPOINTS.ORDERS.CREATE, {
    token: data.token,
    order_type: data.orderType.toLowerCase(),
    wallet_uuid: data.walletUuid,
    wallet_address: data.walletAddress,
    quantity: data.quantity,
    min_quantity: data.minQuantity ?? 0,
    price_per_share: data.pricePerShare,
    message: data.message,
    signature: data.signature,
  });

export const cancelOrder = (apiClient: AxiosInstance, uuid: string, data: SignedCancelOrderRequest) =>
  apiClient.post<TransferOrder>(TRADING_ENDPOINTS.ORDERS.CANCEL(uuid), {
    message: data.message,
    signature: data.signature,
  });

export const getWalletBalances = (apiClient: AxiosInstance, walletAddress: string) =>
  apiClient.get<WalletTokenBalancesResponse>(TRADING_ENDPOINTS.WALLETS.BALANCES, {
    params: { wallet_address: walletAddress },
  });

export const getWhitelistStatus = (apiClient: AxiosInstance, walletAddress: string) =>
  apiClient.get<WhitelistStatus>(TRADING_ENDPOINTS.WHITELIST.STATUS(walletAddress));

export const getSwapOrders = (apiClient: AxiosInstance, walletAddress: string) =>
  apiClient.get<PaginatedResponse<SwapOrder>>(TRADING_ENDPOINTS.SWAPS.LIST, {
    params: { wallet_address: walletAddress },
  });

export const getOrderSwapData = (apiClient: AxiosInstance, orderUuid: string, params: GetSwapDataParams) =>
  apiClient.get<SwapDataResponse>(TRADING_ENDPOINTS.ORDERS.SWAP(orderUuid), {
    params: { wallet_address: params.walletAddress },
  });

export const submitOrderSwapSignature = (apiClient: AxiosInstance, orderUuid: string, data: SubmitSignatureRequest) =>
  apiClient.post<SwapOrder>(TRADING_ENDPOINTS.ORDERS.SWAP_SIGN(orderUuid), {
    signature: data.signature,
    signer_address: data.signerAddress,
  });

export const getOrderSwapApprovalStatus = (apiClient: AxiosInstance, orderUuid: string, walletAddress: string) =>
  apiClient.get<ApprovalStatusResponse>(TRADING_ENDPOINTS.ORDERS.SWAP_APPROVAL_STATUS(orderUuid), {
    params: { wallet_address: walletAddress },
  });

export const getOrderSwapApprovalData = (apiClient: AxiosInstance, orderUuid: string, walletAddress: string) =>
  apiClient.get<ApprovalDataResponse>(TRADING_ENDPOINTS.ORDERS.SWAP_APPROVAL_DATA(orderUuid), {
    params: { wallet_address: walletAddress },
  });

// ============================================================================
// Order Modification Functions
// ============================================================================

/**
 * Get a modification message for signing.
 * This is step 1 of the two-step modification flow.
 */
export const getOrderModificationMessage = (
  apiClient: AxiosInstance,
  orderUuid: string,
  data: OrderModificationRequest,
) =>
  apiClient.post<OrderModificationMessageResponse>(TRADING_ENDPOINTS.ORDERS.MODIFY_MESSAGE(orderUuid), {
    new_quantity: data.newQuantity,
    new_min_quantity: data.newMinQuantity,
    new_price_per_share: data.newPricePerShare,
  });

/**
 * Execute an order modification with a signed message.
 * This is step 2 of the two-step modification flow.
 */
export const modifyOrder = (apiClient: AxiosInstance, orderUuid: string, data: SignedOrderModificationRequest) =>
  apiClient.post<OrderModificationResponse>(TRADING_ENDPOINTS.ORDERS.MODIFY(orderUuid), {
    message: data.message,
    signature: data.signature,
  });

export function parseTradingError(error: unknown): string {
  if (!error) return 'An unknown error occurred';

  const axiosError = error as {
    response?: { data?: { detail?: string; code?: string; message?: string }; status?: number };
    message?: string;
  };

  if (axiosError.response?.data) {
    const data = axiosError.response.data;

    if (data.code === 'not_whitelisted') {
      return 'Your wallet is not verified for trading. Please complete KYC verification to trade tokenized securities.';
    }

    if (data.detail) {
      if (data.detail.includes('not whitelisted')) {
        return 'Your wallet is not verified for trading. Please complete KYC verification to trade tokenized securities.';
      }
      return data.detail;
    }

    if (data.message) return data.message;
  }

  if (axiosError.response?.status === 403) {
    return 'Your wallet is not authorized to trade. Please ensure your wallet is verified and whitelisted.';
  }

  if (axiosError.message) {
    if (axiosError.message.includes('403')) {
      return 'Your wallet is not authorized to trade. Please ensure your wallet is verified and whitelisted.';
    }
    return axiosError.message;
  }

  return 'An error occurred while processing your request';
}
