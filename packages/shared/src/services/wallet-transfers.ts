import { WALLET_ENDPOINTS } from '../constants';
import { AxiosInstance } from 'axios';
import type {
  PrepareTransferRequest,
  PrepareTransferResponse,
  PrepareBitcoinTransferRequest,
  PrepareBitcoinTransferResponse,
  BroadcastTransferRequest,
  BroadcastTransferResponse,
} from '../types';

export const prepareTransfer = (
  apiClient: AxiosInstance,
  uuid: string,
  data: PrepareTransferRequest,
  userAccountUuid?: string,
) =>
  apiClient.post<PrepareTransferResponse>(
    WALLET_ENDPOINTS.PREPARE_TRANSFER(uuid),
    data,
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );

export const prepareBitcoinTransfer = (
  apiClient: AxiosInstance,
  uuid: string,
  data: PrepareBitcoinTransferRequest,
  userAccountUuid?: string,
) =>
  apiClient.post<PrepareBitcoinTransferResponse>(
    WALLET_ENDPOINTS.PREPARE_TRANSFER(uuid),
    data,
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );

export const broadcastTransfer = (
  apiClient: AxiosInstance,
  uuid: string,
  data: BroadcastTransferRequest,
  userAccountUuid?: string,
) =>
  apiClient.post<BroadcastTransferResponse>(
    WALLET_ENDPOINTS.BROADCAST_TRANSFER(uuid),
    data,
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );
