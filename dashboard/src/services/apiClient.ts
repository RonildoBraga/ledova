import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { AUTH_ENDPOINTS, createUserFriendlyError } from '@ledova/shared';

export type { UserFriendlyError } from '@ledova/shared';

type RetriableRequestConfig = InternalAxiosRequestConfig & { csrfRetried?: boolean };

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,

  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  withXSRFToken: true,
});

const isCsrfFailure = (error: AxiosError) => {
  const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
  return error.response?.status === 403 && typeof detail === 'string' && detail.startsWith('CSRF Failed');
};

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const config = error.config as RetriableRequestConfig | undefined;
    if (config && !config.csrfRetried && isCsrfFailure(error)) {
      config.csrfRetried = true;
      return apiClient.get(AUTH_ENDPOINTS.VERIFY).then(() => apiClient.request(config));
    }

    console.error('API Client Error:', error);

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
