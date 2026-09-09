import { AxiosError, AxiosHeaders } from 'axios';
import type { AxiosAdapter, AxiosResponse } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { apiClient, rotateRefreshToken } from './apiClient';
import { clearTokens, getAccessToken, getRefreshToken, storeTokens } from './tokenStorage';

jest.mock('expo-secure-store', () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 7,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const pair = { accessToken: 'synthetic-access', refreshToken: 'synthetic-refresh' };
const rotated = { accessToken: 'rotated-access', refreshToken: 'rotated-refresh' };
const items = new Map<string, string>();

beforeEach(async () => {
  items.clear();
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => items.get(key) ?? null);
  jest.mocked(SecureStore.setItemAsync).mockImplementation(async (key, value) => {
    items.set(key, value);
  });
  jest.mocked(SecureStore.deleteItemAsync).mockImplementation(async (key) => {
    items.delete(key);
  });
  await clearTokens();
  process.env.EXPO_PUBLIC_API_URL = 'https://api.example.test';
  apiClient.defaults.baseURL = process.env.EXPO_PUBLIC_API_URL;
});

function delayedRefresh() {
  let entered!: () => void;
  let resolveResponse!: (value: AxiosResponse) => void;
  let rejectResponse!: (reason: Error) => void;
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const response = new Promise<AxiosResponse>((resolve, reject) => {
    resolveResponse = resolve;
    rejectResponse = reject;
  });
  let requestConfig: Parameters<AxiosAdapter>[0];
  apiClient.defaults.adapter = async (config) => {
    requestConfig = config;
    entered();
    return response;
  };
  return {
    started,
    succeed: () =>
      resolveResponse({
        data: { access: rotated.accessToken, refresh: rotated.refreshToken },
        status: 200,
        statusText: 'OK',
        headers: {},
        config: requestConfig,
      }),
    refuse: () =>
      rejectResponse(
        new AxiosError('Expired', 'ERR_BAD_REQUEST', requestConfig, undefined, {
          data: {},
          status: 401,
          statusText: 'Unauthorized',
          headers: new AxiosHeaders(),
          config: requestConfig,
        }),
      ),
  };
}

it('stores a normal successful rotation and allows an intentional fresh sign-in', async () => {
  await storeTokens(pair);
  const server = delayedRefresh();
  const rotation = rotateRefreshToken(pair.refreshToken);
  await server.started;
  server.succeed();
  await rotation;
  await expect(getRefreshToken()).resolves.toBe(rotated.refreshToken);
  await clearTokens();
  await storeTokens(pair);
  await expect(getAccessToken()).resolves.toBe(pair.accessToken);
});

it('does not restore a session when a refresh resolves after sign-out', async () => {
  await storeTokens(pair);
  const server = delayedRefresh();
  const rotation = rotateRefreshToken(pair.refreshToken);
  const rejected = expect(rotation).rejects.toThrow();
  await server.started;
  await clearTokens();
  server.succeed();
  await rejected;
  await expect(getAccessToken()).resolves.toBeNull();
  await expect(getRefreshToken()).resolves.toBeNull();
});

it.each(['success', 'refusal'])(
  'does not replace or clear a newer sign-in after an old refresh %s',
  async (outcome) => {
    await storeTokens(pair);
    const server = delayedRefresh();
    const rotation = rotateRefreshToken(pair.refreshToken);
    const rejected = expect(rotation).rejects.toThrow();
    await server.started;
    await storeTokens({ accessToken: 'new-sign-in-access', refreshToken: 'new-sign-in-refresh' });
    if (outcome === 'success') server.succeed();
    else server.refuse();
    await rejected;
    await expect(getAccessToken()).resolves.toBe('new-sign-in-access');
    await expect(getRefreshToken()).resolves.toBe('new-sign-in-refresh');
  },
);

it('retains intentional biometric sign-in from an otherwise absent ordinary session', async () => {
  const server = delayedRefresh();
  const rotation = rotateRefreshToken('synthetic-gated-refresh');
  await server.started;
  server.succeed();
  await rotation;
  await expect(getRefreshToken()).resolves.toBe(rotated.refreshToken);
});
