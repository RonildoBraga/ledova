import { AxiosInstance } from 'axios';
import type {
  PrepareTransferRequest,
  PrepareTransferResponse,
  PrepareBitcoinTransferRequest,
  PrepareBitcoinTransferResponse,
  BroadcastTransferRequest,
  BroadcastTransferResponse,
} from '../types';

const postWalletTransfer = <T>(
  apiClient: AxiosInstance,
  url: string,
  data: PrepareTransferRequest | PrepareBitcoinTransferRequest | BroadcastTransferRequest,
  userAccountUuid?: string,
) =>
  userAccountUuid
    ? apiClient.post<T>(url, data, { params: { user_account: userAccountUuid } })
    : apiClient.post<T>(url, data);

export const prepareTransfer = (
  apiClient: AxiosInstance,
  uuid: string,
  data: PrepareTransferRequest,
  userAccountUuid?: string,
) =>
  postWalletTransfer<PrepareTransferResponse>(
    apiClient,
    `/api/wallets/${uuid}/prepare-transfer/`,
    data,
    userAccountUuid,
  );

export const prepareBitcoinTransfer = (
  apiClient: AxiosInstance,
  uuid: string,
  data: PrepareBitcoinTransferRequest,
  userAccountUuid?: string,
) =>
  postWalletTransfer<PrepareBitcoinTransferResponse>(
    apiClient,
    `/api/wallets/${uuid}/prepare-transfer/`,
    data,
    userAccountUuid,
  );

export const broadcastTransfer = (
  apiClient: AxiosInstance,
  uuid: string,
  data: BroadcastTransferRequest,
  userAccountUuid?: string,
) =>
  postWalletTransfer<BroadcastTransferResponse>(
    apiClient,
    `/api/wallets/${uuid}/broadcast-transfer/`,
    data,
    userAccountUuid,
  );
