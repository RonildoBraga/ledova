import type { AxiosInstance, AxiosRequestConfig } from 'axios';
import { TRADING_ENDPOINTS } from '../constants';
import type {
  SettlementSwapOrder,
  SwapSettlementApprovalConfirmed,
  SwapSettlementApprovalData,
  SwapSettlementApprovalStatus,
  SwapSettlementIdentity,
  SwapSettlementLookup,
  SwapSettlementResponse,
  SwapSettlementSignature,
} from '../types';

const identityBody = (identity: SwapSettlementLookup) => ({
  swap_uuid: identity.swapUuid,
  owner_account_uuid: identity.ownerAccountUuid,
  wallet_uuid: identity.walletUuid,
  ...(identity.settlementDigest === undefined ? {} : { settlement_digest: identity.settlementDigest }),
});

export const getSwapSettlementContext = (
  apiClient: AxiosInstance,
  identity: SwapSettlementLookup,
  config?: AxiosRequestConfig,
) =>
  apiClient.get<SwapSettlementResponse>(TRADING_ENDPOINTS.ORDERS.SWAP(identity.orderUuid), {
    ...config,
    params: { ...config?.params, ...identityBody(identity) },
  });

export const submitSwapSettlementSignature = (
  apiClient: AxiosInstance,
  identity: SwapSettlementIdentity,
  signature: SwapSettlementSignature,
  config?: AxiosRequestConfig,
) =>
  apiClient.post<SettlementSwapOrder>(
    TRADING_ENDPOINTS.ORDERS.SWAP_SIGN(identity.orderUuid),
    { ...identityBody(identity), signature: signature.signature, signer_address: signature.signerAddress },
    config,
  );

export const getSwapSettlementApprovalStatus = (
  apiClient: AxiosInstance,
  identity: SwapSettlementIdentity,
  config?: AxiosRequestConfig,
) =>
  apiClient.get<SwapSettlementApprovalStatus>(TRADING_ENDPOINTS.ORDERS.SWAP_APPROVAL_STATUS(identity.orderUuid), {
    ...config,
    params: { ...config?.params, ...identityBody(identity) },
  });

export const getSwapSettlementApprovalData = (
  apiClient: AxiosInstance,
  identity: SwapSettlementIdentity,
  config?: AxiosRequestConfig,
) =>
  apiClient.get<SwapSettlementApprovalData>(TRADING_ENDPOINTS.ORDERS.SWAP_APPROVAL_DATA(identity.orderUuid), {
    ...config,
    params: { ...config?.params, ...identityBody(identity) },
  });

export const broadcastSwapSettlementApproval = (
  apiClient: AxiosInstance,
  identity: SwapSettlementIdentity,
  signedTransaction: string,
  config?: AxiosRequestConfig,
) =>
  apiClient.post<SwapSettlementApprovalConfirmed>(
    TRADING_ENDPOINTS.ORDERS.SWAP_APPROVAL_BROADCAST(identity.orderUuid),
    { ...identityBody(identity), signed_transaction: signedTransaction },
    config,
  );
