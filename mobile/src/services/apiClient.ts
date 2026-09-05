import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import {
  API_CONFIG,
  AUTH_ENDPOINTS,
  refreshToken as requestTokenRefresh,
  createUserFriendlyError,
} from '@ledova/shared';
import { clearTokens, getAccessToken, getRefreshToken, storeTokens } from './tokenStorage';

export type { UserFriendlyError } from '@ledova/shared';

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
  const accessToken = await getAccessToken();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

/**
 * Exchanges a refresh token for a rotated pair and stores it (tokenStorage keeps the biometric-gated
 * copy in step). When the backend rejects the token (revoked by a sign-out, expired, already rotated)
 * every stored token is cleared; a network failure leaves them in place. Rethrows either way.
 */
export async function rotateRefreshToken(refresh: string): Promise<void> {
  try {
    const { data } = await requestTokenRefresh(apiClient, { refresh });
    await storeTokens({ accessToken: data.access, refreshToken: data.refresh });
  } catch (error) {
    if (axios.isAxiosError(error) && error.response) {
      await clearTokens();
    }
    throw error;
  }
}

// A 401 from these endpoints is the answer itself, never a stale access token.
const REFRESH_EXEMPT_URLS = new Set<string>([
  AUTH_ENDPOINTS.SIGNIN,
  AUTH_ENDPOINTS.SIGNOUT,
  AUTH_ENDPOINTS.TOKEN_REFRESH,
]);

// Concurrent 401s share one refresh so a burst of expired requests rotates the token once.
let refreshInFlight: Promise<boolean> | null = null;

function refreshStoredSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refresh = await getRefreshToken();
      if (!refresh) {
        return false;
      }
      try {
        await rotateRefreshToken(refresh);
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

    // An expired access token: refresh once and replay the request, which picks up the new Bearer header.
    // When the refresh fails the tokens are gone and the 401 reaches the caller.
    const config = error.config as ReplayableRequestConfig | undefined;
    if (error.response?.status === 401 && config && !config._retry && !REFRESH_EXEMPT_URLS.has(config.url ?? '')) {
      config._retry = true;
      if (await refreshStoredSession()) {
        return apiClient(config);
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
