import { AxiosInstance } from 'axios';
import type {
  RequestVerificationChallengeResponse,
  VerifyWalletRequest,
  VerifyWalletResponse,
  SyncWalletResponse,
} from '../types';

export const requestVerificationChallenge = (apiClient: AxiosInstance, uuid: string, userAccountUuid?: string) =>
  apiClient.post<RequestVerificationChallengeResponse>(
    `/api/wallets/${uuid}/request-verification/`,
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
    `/api/wallets/${uuid}/verify-signature/`,
    data,
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );

export const syncWallet = (apiClient: AxiosInstance, uuid: string, userAccountUuid?: string) =>
  apiClient.post<SyncWalletResponse>(
    `/api/wallets/${uuid}/sync/`,
    {},
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );
