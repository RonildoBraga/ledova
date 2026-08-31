import axios, { AxiosError } from 'axios';
import { createUserFriendlyError } from '@ledova/shared-utils';

export type { UserFriendlyError } from '@ledova/shared-types';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// Response interceptor for better error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    console.error('API Client Error:', error);

    // Network/timeout errors
    if (!error.response) {
      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        return Promise.reject(
          createUserFriendlyError('Request timed out. Please check your connection and try again.', error),
        );
      }

      if (
        error.code === 'ERR_NETWORK' ||
        error.message?.includes('Network Error') ||
        error.message?.includes('ECONNREFUSED') ||
        error.message?.includes('ENOTFOUND')
      ) {
        return Promise.reject(
          createUserFriendlyError(
            'Unable to connect to our servers. Please check your internet connection and try again.',
            error,
          ),
        );
      }
    }

    // Server errors (5xx)
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

export default apiClient;
