import { AxiosInstance } from 'axios';
import { FEATURE_FLAG_ENDPOINTS } from '@ledova/shared-constants';
import type { FeatureFlag, PaginatedResponse } from '@ledova/shared-types';

export const getFeatureFlags = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<FeatureFlag>>(FEATURE_FLAG_ENDPOINTS.BASE);
