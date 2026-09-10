import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import {
  API_CONFIG,
  AUTH_ENDPOINTS,
  refreshToken as requestTokenRefresh,
  createUserFriendlyError,
  hasServiceErrorDetail,
} from '@ledova/shared';
import { captureRefreshSession, clearTokens, getAccessToken, getRefreshToken, storeTokens } from './tokenStorage';
import { getApiBaseUrl, validateApiDestination } from '../config/networkPolicy';
import { assertSessionEpoch } from './sessionScope';

declare module 'axios' {
  interface AxiosRequestConfig {
    ledovaSessionEpoch?: number;
  }
}

export type { UserFriendlyError } from '@ledova/shared';

const apiClient = axios.create({
  baseURL: process.env.EXPO_PUBLIC_API_URL,
  timeout: API_CONFIG.DEFAULT_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',

    'X-Auth-Transport': 'bearer',
  },

  withCredentials: false,
});

apiClient.interceptors.request.use(async (config) => {
  config.baseURL = config.baseURL ?? getApiBaseUrl();
  validateApiDestination(apiClient.getUri(config));
  if (config.auth) throw new Error('The mobile API uses the stored bearer session.');
  if (config.ledovaSessionEpoch !== undefined) assertSessionEpoch(config.ledovaSessionEpoch);
  const accessToken = await getAccessToken();
  if (config.ledovaSessionEpoch !== undefined) {
    assertSessionEpoch(config.ledovaSessionEpoch);
    if (!accessToken) throw new Error('Please sign in again before uploading a document.');
  }
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  } else {
    config.headers.delete('Authorization');
  }
  return config;
});

export async function rotateRefreshToken(refresh: string, expectedEpoch?: number): Promise<void> {
  if (expectedEpoch !== undefined) assertSessionEpoch(expectedEpoch);
  const generation = await captureRefreshSession(refresh);
  if (expectedEpoch !== undefined) assertSessionEpoch(expectedEpoch);
  try {
    const { data } = await requestTokenRefresh(
      apiClient,
      { refresh },
      expectedEpoch === undefined ? undefined : { ledovaSessionEpoch: expectedEpoch },
    );
    await storeTokens({ accessToken: data.access, refreshToken: data.refresh }, generation);
  } catch (error) {
    if (axios.isAxiosError(error) && error.response) {
      await clearTokens(generation);
    }
    throw error;
  }
}

const REFRESH_EXEMPT_URLS = new Set<string>([
  AUTH_ENDPOINTS.SIGNIN,
  AUTH_ENDPOINTS.SIGNOUT,
  AUTH_ENDPOINTS.TOKEN_REFRESH,
]);

let refreshInFlight: Promise<boolean> | null = null;

function refreshStoredSession(expectedEpoch?: number): Promise<boolean> {
  if (expectedEpoch !== undefined) assertSessionEpoch(expectedEpoch);
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refresh = await getRefreshToken();
      if (expectedEpoch !== undefined) assertSessionEpoch(expectedEpoch);
      if (!refresh) {
        return false;
      }
      try {
        await rotateRefreshToken(refresh, expectedEpoch);
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

interface ReplayableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
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

    const config = error.config as ReplayableRequestConfig | undefined;
    if (config?.ledovaSessionEpoch !== undefined) assertSessionEpoch(config.ledovaSessionEpoch);
    if (error.response?.status === 401 && config && !config._retry && !REFRESH_EXEMPT_URLS.has(config.url ?? '')) {
      config._retry = true;
      if (await refreshStoredSession(config.ledovaSessionEpoch)) {
        return apiClient(config);
      }
    }

    if (error.response?.status && error.response.status >= 500) {
      if (error.response.status === 503 && hasServiceErrorDetail(error)) {
        return Promise.reject(error);
      }

      return Promise.reject(
        createUserFriendlyError('Our servers are temporarily unavailable. Please try again in a few moments.', error),
      );
    }

    return Promise.reject(error);
  },
);

export { apiClient };
