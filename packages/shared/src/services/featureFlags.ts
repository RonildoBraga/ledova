import { AxiosInstance } from 'axios';
import { FEATURE_FLAG_ENDPOINTS } from '../constants';
import type { FeatureFlag, PaginatedResponse } from '../types';

export const getFeatureFlags = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<FeatureFlag>>(FEATURE_FLAG_ENDPOINTS.BASE);
