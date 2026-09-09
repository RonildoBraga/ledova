import { WALLET_ENDPOINTS } from '../constants';
import { AxiosInstance } from 'axios';
import { createUserFriendlyError } from '../utils/errors';
import type {
  RequestVerificationChallengeResponse,
  VerifyWalletRequest,
  VerifyWalletResponse,
  SyncWalletResponse,
} from '../types';

const SYNC_FAILED = 'Wallet sync could not finish. Please try again later.';
const VERIFY_BEFORE_SYNC = 'Verify this wallet before syncing it.';
const SAFE_SYNC_ERRORS = new Set([
  SYNC_FAILED,
  VERIFY_BEFORE_SYNC,
  'Some wallet balances could not be refreshed. Please try again later.',
  'Some wallet transaction history could not be read. Please try again later.',
]);

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
    const { status, error } = response.data.syncResult;
    const message =
      status === 'skipped' ? VERIFY_BEFORE_SYNC : error && SAFE_SYNC_ERRORS.has(error) ? error : SYNC_FAILED;
    throw createUserFriendlyError(message);
  }
  return response;
};
