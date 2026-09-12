import type { AxiosInstance, AxiosRequestConfig } from 'axios';
import { TRADING_ENDPOINTS } from '../constants';
import type {
  ShareToken,
  TransferOrder,
  OrderSubmissionRequest,
  OrderSubmissionSnapshot,
  OrderActionContext,
  OrderActionSnapshot,
  OrderActionRequest,
  OrderActionModificationRequest,
  OrderActionExecuteRequest,
  OrderBook,
  GetOrdersParams,
  WhitelistStatus,
  SwapOrder,
  SwapDataResponse,
  SubmitSignatureRequest,
  GetSwapDataParams,
  SignedCreateOrderRequest,
  WalletTokenBalancesResponse,
  MarketData,
  PaginatedResponse,
  ApprovalStatusResponse,
  ApprovalDataResponse,
} from '../types';

declare module 'axios' {
  interface AxiosRequestConfig {
    ledovaSubmissionGuard?: () => void;
  }
}

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

const orderSubmissionBody = (data: OrderSubmissionRequest) => ({
  submission_id: data.submissionId,
  owner_account_uuid: data.ownerAccountUuid,
  token: data.token,
  order_type: data.orderType.toLowerCase(),
  wallet_uuid: data.walletUuid,
  wallet_address: data.walletAddress,
  quantity: data.quantity,
  min_quantity: data.minQuantity ?? 0,
  price_per_share: data.pricePerShare,
});

export const getOrderCreateMessage = (
  apiClient: AxiosInstance,
  data: OrderSubmissionRequest,
  config?: AxiosRequestConfig,
) =>
  apiClient.post<OrderSubmissionSnapshot>(TRADING_ENDPOINTS.ORDERS.CREATE_MESSAGE, orderSubmissionBody(data), config);

export const getOrderSubmission = (
  apiClient: AxiosInstance,
  submissionId: string,
  ownerAccountUuid: string,
  config?: AxiosRequestConfig,
) =>
  apiClient.get<OrderSubmissionSnapshot>(TRADING_ENDPOINTS.ORDERS.SUBMISSION(submissionId), {
    ...config,
    params: { owner_account_uuid: ownerAccountUuid },
  });

export const getOrderActionContext = (
  apiClient: AxiosInstance,
  uuid: string,
  ownerAccountUuid: string,
  config?: AxiosRequestConfig,
) =>
  apiClient.get<OrderActionContext>(TRADING_ENDPOINTS.ORDERS.ACTION_CONTEXT(uuid), {
    ...config,
    params: { owner_account_uuid: ownerAccountUuid },
  });

export const getOrderAction = (
  apiClient: AxiosInstance,
  actionId: string,
  ownerAccountUuid: string,
  config?: AxiosRequestConfig,
) =>
  apiClient.get<OrderActionSnapshot>(TRADING_ENDPOINTS.ORDERS.ACTION(actionId), {
    ...config,
    params: { owner_account_uuid: ownerAccountUuid },
  });

export const getOrderCancelMessage = (
  apiClient: AxiosInstance,
  uuid: string,
  data: OrderActionRequest,
  config?: AxiosRequestConfig,
) =>
  apiClient.post<OrderActionSnapshot>(
    TRADING_ENDPOINTS.ORDERS.CANCEL_MESSAGE(uuid),
    {
      action_id: data.actionId,
      owner_account_uuid: data.ownerAccountUuid,
    },
    config,
  );

export const createOrder = (apiClient: AxiosInstance, data: SignedCreateOrderRequest, config?: AxiosRequestConfig) =>
  apiClient.post<OrderSubmissionSnapshot>(
    TRADING_ENDPOINTS.ORDERS.CREATE,
    {
      ...orderSubmissionBody(data),
      digest: data.digest,
      signature: data.signature,
    },
    config,
  );

export const cancelOrder = (
  apiClient: AxiosInstance,
  uuid: string,
  data: OrderActionExecuteRequest,
  config?: AxiosRequestConfig,
) =>
  apiClient.post<OrderActionSnapshot>(
    TRADING_ENDPOINTS.ORDERS.CANCEL(uuid),
    {
      action_id: data.actionId,
      owner_account_uuid: data.ownerAccountUuid,
      digest: data.digest,
      signature: data.signature,
    },
    config,
  );

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

export const getOrderModificationMessage = (
  apiClient: AxiosInstance,
  orderUuid: string,
  data: OrderActionModificationRequest,
  config?: AxiosRequestConfig,
) =>
  apiClient.post<OrderActionSnapshot>(
    TRADING_ENDPOINTS.ORDERS.MODIFY_MESSAGE(orderUuid),
    {
      action_id: data.actionId,
      owner_account_uuid: data.ownerAccountUuid,
      new_quantity: data.newQuantity,
      new_min_quantity: data.newMinQuantity,
      new_price_per_share: data.newPricePerShare,
    },
    config,
  );

export const modifyOrder = (
  apiClient: AxiosInstance,
  orderUuid: string,
  data: OrderActionExecuteRequest,
  config?: AxiosRequestConfig,
) =>
  apiClient.post<OrderActionSnapshot>(
    TRADING_ENDPOINTS.ORDERS.MODIFY(orderUuid),
    {
      action_id: data.actionId,
      owner_account_uuid: data.ownerAccountUuid,
      digest: data.digest,
      signature: data.signature,
    },
    config,
  );

export function parseTradingError(error: unknown): string {
  if (!error) return 'An unknown error occurred';

  const axiosError = error as {
    response?: { data?: { detail?: string; code?: string; message?: string }; status?: number };
    message?: string;
  };

  if (axiosError.response?.data) {
    const data = axiosError.response.data;

    if (data.code === 'not_whitelisted') {
      return 'Your wallet is not on the trading allowlist. The operator must add it before you can place orders.';
    }

    if (data.detail) {
      if (data.detail.includes('not whitelisted')) {
        return 'Your wallet is not on the trading allowlist. The operator must add it before you can place orders.';
      }
      return data.detail;
    }

    if (data.message) return data.message;
  }

  if (axiosError.response?.status === 403) {
    return 'Your wallet is not authorized to trade. The operator must add it to the trading allowlist.';
  }

  if (axiosError.message) {
    if (axiosError.message.includes('403')) {
      return 'Your wallet is not authorized to trade. The operator must add it to the trading allowlist.';
    }
    return axiosError.message;
  }

  return 'An error occurred while processing your request';
}
