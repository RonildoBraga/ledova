import axios, { AxiosError } from 'axios';
import { API_CONFIG } from '@ledova/shared-constants';
import { createUserFriendlyError } from '@ledova/shared-utils';
import * as SecureStore from 'expo-secure-store';

export type { UserFriendlyError } from '@ledova/shared-types';

const apiClient = axios.create({
  baseURL: process.env.EXPO_PUBLIC_API_URL,
  timeout: API_CONFIG.DEFAULT_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
    // Asks sign-in, email verification and token refresh for the pair in the body and no cookies.
    'X-Auth-Transport': 'bearer',
  },
  // Auth is the Bearer header from SecureStore. React Native's XMLHttpRequest defaults
  // withCredentials to true, which stores the sign-in cookies and replays them beside the header.
  withCredentials: false,
});

apiClient.interceptors.request.use(async (config) => {
  const accessToken = await SecureStore.getItemAsync('accessToken');
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (!error.response) {
      if (error.code === AxiosError.ECONNABORTED) {
        return Promise.reject(
          createUserFriendlyError('Request timed out. Please check your connection and try again.', error),
        );
      }

      if (error.code === AxiosError.ERR_NETWORK) {
        return Promise.reject(
          createUserFriendlyError(
            'Unable to connect to our servers. Please check your internet connection and try again.',
            error,
          ),
        );
      }
    }

    if (error.response?.status && error.response.status >= 500) {
      if (typeof error.response.data === 'string' && error.response.data.includes('<html>')) {
        return Promise.reject(
          createUserFriendlyError('Our servers are temporarily unavailable. Please try again in a few moments.', error),
        );
      }

      return Promise.reject(
        createUserFriendlyError('Our servers are temporarily unavailable. Please try again in a few moments.', error),
      );
    }

    return Promise.reject(error);
  },
);

export { apiClient };
