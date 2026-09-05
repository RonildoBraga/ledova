import { AxiosInstance } from 'axios';
import { IDENTITY_VERIFICATION_ENDPOINTS } from '../constants';
import type { IdentityVerificationToken, IdentityVerificationStatus } from '../types';

export const getIdentityVerificationToken = (apiClient: AxiosInstance) => {
  return apiClient.post<IdentityVerificationToken>(IDENTITY_VERIFICATION_ENDPOINTS.TOKEN);
};

export const getIdentityVerificationStatus = (apiClient: AxiosInstance) => {
  return apiClient.get<IdentityVerificationStatus>(IDENTITY_VERIFICATION_ENDPOINTS.STATUS);
};
