import { AxiosInstance } from 'axios';
import type { Wallet, CreateWallet, WalletQueryParams, PaginatedResponse } from '../types';

export const getWallets = (apiClient: AxiosInstance, params?: WalletQueryParams) =>
  apiClient.get<PaginatedResponse<Wallet>>('/api/wallets/', { params });

export const createWallet = (apiClient: AxiosInstance, data: CreateWallet) =>
  apiClient.post<Wallet>('/api/wallets/', data);

export const updateWallet = (apiClient: AxiosInstance, uuid: string, data: Partial<Pick<Wallet, 'name'>>) =>
  apiClient.patch<Wallet>(`/api/wallets/${uuid}/`, data);

export const deleteWallet = (apiClient: AxiosInstance, uuid: string, userAccountUuid?: string) =>
  apiClient.delete(
    `/api/wallets/${uuid}/`,
    userAccountUuid ? { params: { user_account: userAccountUuid } } : undefined,
  );
