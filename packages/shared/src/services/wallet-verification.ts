import { WALLET_ENDPOINTS } from '../constants';
import { AxiosInstance } from 'axios';
import { createUserFriendlyError } from '../utils/errors';
import type {
  RequestVerificationChallengeResponse,
  VerifyWalletRequest,
  VerifyWalletResponse,
  SyncWalletResponse,
} from '../types';

export const requestVerificationChallenge = (apiClient: AxiosInstance, uuid: string, userAccountUuid?: string) =>
  apiClient.post<RequestVerificationChallengeResponse>(
    WALLET_ENDPOINTS.REQUEST_VERIFICATION(uuid),
    {},
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );

export const verifyWalletSignature = (
  apiClient: AxiosInstance,
  uuid: string,
  data: VerifyWalletRequest,
  userAccountUuid?: string,
) =>
  apiClient.post<VerifyWalletResponse>(
    WALLET_ENDPOINTS.VERIFY_SIGNATURE(uuid),
    data,
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );

export const syncWallet = async (apiClient: AxiosInstance, uuid: string, userAccountUuid?: string) => {
  const response = await apiClient.post<SyncWalletResponse>(
    WALLET_ENDPOINTS.SYNC(uuid),
    {},
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );
  if (!response.data.success || response.data.syncResult.status !== 'success') {
    throw createUserFriendlyError(
      response.data.syncResult.error || 'Wallet sync could not finish. Please try again later.',
    );
  }
  return response;
};
