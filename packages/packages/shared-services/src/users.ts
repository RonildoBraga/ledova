import { AxiosInstance } from 'axios';
import { USER_PROFILE_ENDPOINTS } from '@ledova/shared-constants';
import type {
  UserProfile,
  UpdateUserProfile,
  CompleteUserProfile,
  PaginatedResponse,
  AccountExportData,
} from '@ledova/shared-types';

export const updateUserProfile = (apiClient: AxiosInstance, uuid: string, data: UpdateUserProfile) =>
  apiClient.patch<UserProfile>(`${USER_PROFILE_ENDPOINTS.BASE}${uuid}/`, data);

export const updateUserProfileCompletion = (apiClient: AxiosInstance, uuid: string, data: CompleteUserProfile) =>
  apiClient.patch<UserProfile>(`${USER_PROFILE_ENDPOINTS.BASE}${uuid}/`, data);

export const getUserProfiles = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<UserProfile>>(USER_PROFILE_ENDPOINTS.BASE);

export const deleteAccount = (apiClient: AxiosInstance) =>
  apiClient.post<{ message: string }>(USER_PROFILE_ENDPOINTS.DELETE_ACCOUNT);

export const exportAccountData = (apiClient: AxiosInstance) =>
  apiClient.get<AccountExportData>(USER_PROFILE_ENDPOINTS.EXPORT_DATA);
