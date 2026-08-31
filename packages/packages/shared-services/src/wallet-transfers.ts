import { AxiosInstance } from 'axios';
import type {
  PrepareTransferRequest,
  PrepareTransferResponse,
  BroadcastTransferRequest,
  BroadcastTransferResponse,
} from '@ledova/shared-types';

export const prepareTransfer = (
  apiClient: AxiosInstance,
  uuid: string,
  data: PrepareTransferRequest,
  userAccountUuid?: string,
) => {
  if (userAccountUuid) {
    return apiClient.post<PrepareTransferResponse>(`/api/wallets/${uuid}/prepare-transfer/`, data, {
      params: { user_account: userAccountUuid },
    });
  }
  return apiClient.post<PrepareTransferResponse>(`/api/wallets/${uuid}/prepare-transfer/`, data);
};

export const broadcastTransfer = (
  apiClient: AxiosInstance,
  uuid: string,
  data: BroadcastTransferRequest,
  userAccountUuid?: string,
) => {
  if (userAccountUuid) {
    return apiClient.post<BroadcastTransferResponse>(`/api/wallets/${uuid}/broadcast-transfer/`, data, {
      params: { user_account: userAccountUuid },
    });
  }
  return apiClient.post<BroadcastTransferResponse>(`/api/wallets/${uuid}/broadcast-transfer/`, data);
};
