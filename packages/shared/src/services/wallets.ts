import { WALLET_ENDPOINTS } from '../constants';
import { AxiosInstance } from 'axios';
import type { Wallet, CreateWallet, WalletQueryParams, PaginatedResponse } from '../types';

export const getWallets = (apiClient: AxiosInstance, params?: WalletQueryParams) =>
  apiClient.get<PaginatedResponse<Wallet>>(WALLET_ENDPOINTS.BASE, { params });

export const createWallet = (apiClient: AxiosInstance, data: CreateWallet) =>
  apiClient.post<Wallet>(WALLET_ENDPOINTS.BASE, data);

export const updateWallet = (apiClient: AxiosInstance, uuid: string, data: Partial<Pick<Wallet, 'name'>>) =>
  apiClient.patch<Wallet>(WALLET_ENDPOINTS.DETAIL(uuid), data);

export const deleteWallet = (apiClient: AxiosInstance, uuid: string, userAccountUuid?: string) =>
  apiClient.delete(
    WALLET_ENDPOINTS.DETAIL(uuid),
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );
