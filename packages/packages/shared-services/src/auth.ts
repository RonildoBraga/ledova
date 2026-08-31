import { AxiosInstance } from 'axios';
import { AUTH_ENDPOINTS } from '@ledova/shared-constants';
import type {
  SigninRequest,
  SignupRequest,
  EmailVerificationRequest,
  TokenRefreshResult,
  TokenRefreshRequest,
  AuthVerificationResponse,
  ChangePasswordRequest,
  ChangePasswordResponse,
} from '@ledova/shared-types';

export const signin = (apiClient: AxiosInstance, data: SigninRequest) => {
  return apiClient.post(AUTH_ENDPOINTS.SIGNIN, data);
};

export const signout = (apiClient: AxiosInstance) => {
  return apiClient.post(AUTH_ENDPOINTS.SIGNOUT);
};

export const signup = (apiClient: AxiosInstance, data: SignupRequest) => {
  return apiClient.post(AUTH_ENDPOINTS.SIGNUP, data);
};

export const verifyEmail = (apiClient: AxiosInstance, data: EmailVerificationRequest) => {
  return apiClient.post(AUTH_ENDPOINTS.EMAIL_VERIFICATION, data);
};

export const resendVerificationCode = (apiClient: AxiosInstance) => {
  return apiClient.post(AUTH_ENDPOINTS.RESEND_VERIFICATION);
};

export const refreshToken = (apiClient: AxiosInstance, data: TokenRefreshRequest) => {
  return apiClient.post<TokenRefreshResult>(AUTH_ENDPOINTS.TOKEN_REFRESH, data);
};

export const verifyAuth = (apiClient: AxiosInstance) => {
  return apiClient.get<AuthVerificationResponse>(AUTH_ENDPOINTS.VERIFY);
};

export const changePassword = (apiClient: AxiosInstance, data: ChangePasswordRequest) => {
  return apiClient.post<ChangePasswordResponse>(AUTH_ENDPOINTS.CHANGE_PASSWORD, data);
};
