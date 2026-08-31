import { AxiosInstance, AxiosResponse } from 'axios';
import type { Transaction, TransactionQueryParams, PaginatedResponse } from '@ledova/shared-types';
import { getNextPageParam } from '@ledova/shared-utils';

export const getTransactions = (apiClient: AxiosInstance, params?: TransactionQueryParams) =>
  apiClient.get<PaginatedResponse<Transaction>>('/api/transactions/', { params });

export const getTransactionsNextPage = (lastPage: AxiosResponse<PaginatedResponse<Transaction>>): number | undefined =>
  getNextPageParam(lastPage.data);
