import { AxiosInstance } from 'axios';
import { USER_PREFERENCES_ENDPOINTS } from '../constants';
import type { UserPreferences, UpdateUserPreferences } from '../types';

export const getCurrentUserPreferences = (apiClient: AxiosInstance) => {
  return apiClient.get<UserPreferences>(USER_PREFERENCES_ENDPOINTS.BASE);
};

export const upsertCurrentUserPreferences = (apiClient: AxiosInstance, data: UpdateUserPreferences) => {
  return apiClient.post<UserPreferences>(USER_PREFERENCES_ENDPOINTS.BASE, data);
};
