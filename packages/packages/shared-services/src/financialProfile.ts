import { AxiosInstance } from 'axios';
import { FINANCIAL_PROFILE_ENDPOINTS } from '@ledova/shared-constants';
import type {
  FinancialProfile,
  CreateFinancialProfile,
  UpdateFinancialProfile,
  PaginatedResponse,
} from '@ledova/shared-types';

export const createFinancialProfile = (apiClient: AxiosInstance, data: CreateFinancialProfile) =>
  apiClient.post<FinancialProfile>(FINANCIAL_PROFILE_ENDPOINTS.BASE, data);

export const updateFinancialProfile = (apiClient: AxiosInstance, uuid: string, data: UpdateFinancialProfile) =>
  apiClient.patch<FinancialProfile>(FINANCIAL_PROFILE_ENDPOINTS.DETAIL(uuid), data);

export const getFinancialProfiles = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<FinancialProfile>>(FINANCIAL_PROFILE_ENDPOINTS.BASE);
