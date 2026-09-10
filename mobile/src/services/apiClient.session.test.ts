import { AxiosError, AxiosHeaders } from 'axios';
import type { AxiosAdapter, AxiosResponse } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { apiClient, rotateRefreshToken } from './apiClient';
import { clearTokens, getAccessToken, getRefreshToken, storeTokens } from './tokenStorage';
import { getSessionEpoch } from './sessionScope';
import { AUTH_ENDPOINTS } from '@ledova/shared';

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
    const newEpoch = getSessionEpoch();
    if (outcome === 'success') server.succeed();
    else server.refuse();
    await rejected;
    await expect(getAccessToken()).resolves.toBe('new-sign-in-access');
    await expect(getRefreshToken()).resolves.toBe('new-sign-in-refresh');
    expect(getSessionEpoch()).toBe(newEpoch);
  },
);

it('retains intentional biometric sign-in from an otherwise absent ordinary session', async () => {
  const epoch = getSessionEpoch();
  const server = delayedRefresh();
  const rotation = rotateRefreshToken('synthetic-gated-refresh');
  await server.started;
  server.succeed();
  await rotation;
  await expect(getRefreshToken()).resolves.toBe(rotated.refreshToken);
  expect(getSessionEpoch()).not.toBe(epoch);
});

function expired(config: Parameters<AxiosAdapter>[0]): AxiosError {
  return new AxiosError('Expired', 'ERR_BAD_REQUEST', config, undefined, {
    data: {},
    status: 401,
    statusText: 'Unauthorized',
    headers: new AxiosHeaders(),
    config,
  });
}

it('replays a scoped upload within the same session after ordinary rotation', async () => {
  await storeTokens(pair);
  const epoch = getSessionEpoch();
  const requests: Parameters<AxiosAdapter>[0][] = [];
  apiClient.defaults.adapter = async (config) => {
    requests.push(config);
    if (requests.length === 1) throw expired(config);
    return {
      data:
        config.url === AUTH_ENDPOINTS.TOKEN_REFRESH
          ? { access: rotated.accessToken, refresh: rotated.refreshToken }
          : { accepted: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    };
  };
  const response = await apiClient.post('/documents/', { document: 'synthetic' }, { ledovaSessionEpoch: epoch });
  expect(response.data).toEqual({ accepted: true });
  expect(requests.map(({ url }) => url)).toEqual(['/documents/', AUTH_ENDPOINTS.TOKEN_REFRESH, '/documents/']);
  expect(requests[2].headers.Authorization).toBe(`Bearer ${rotated.accessToken}`);
  expect(requests[2].data).toBe(requests[0].data);
  expect(requests.every((config) => config.ledovaSessionEpoch === epoch)).toBe(true);
  expect(getSessionEpoch()).toBe(epoch);
});

it('does not refresh or replay an old upload when its refusal arrives after a fresh login', async () => {
  await storeTokens(pair);
  const epoch = getSessionEpoch();
  let refuse!: () => void;
  let entered!: () => void;
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const requests: string[] = [];
  apiClient.defaults.adapter = async (config) => {
    requests.push(config.url!);
    if (requests.length > 1) {
      return {
        data:
          config.url === AUTH_ENDPOINTS.TOKEN_REFRESH
            ? { access: rotated.accessToken, refresh: rotated.refreshToken }
            : { accepted: true },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
    }
    return new Promise((_, reject) => {
      refuse = () => reject(expired(config));
      entered();
    });
  };
  const upload = apiClient.post('/documents/', { document: 'old' }, { ledovaSessionEpoch: epoch });
  const refused = expect(upload).rejects.toThrow('session changed');
  await started;
  await storeTokens({ accessToken: 'new-access', refreshToken: 'new-refresh' });
  refuse();
  await refused;
  expect(requests).toEqual(['/documents/']);
  await expect(getRefreshToken()).resolves.toBe('new-refresh');
});

it.each([1, 2])('refuses the old upload if login changes during credential read %s', async (blockedRead) => {
  await storeTokens(pair);
  const epoch = getSessionEpoch();
  const read = jest.mocked(SecureStore.getItemAsync).getMockImplementation()!;
  let reads = 0;
  let release!: () => void;
  let entered!: () => void;
  const blocked = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const released = new Promise<void>((resolve) => {
    release = resolve;
  });
  jest.mocked(SecureStore.getItemAsync).mockImplementation(async (key) => {
    if (key === 'session.tokens.v2' && ++reads === blockedRead) {
      entered();
      await released;
    }
    return read(key);
  });
  const requests: string[] = [];
  apiClient.defaults.adapter = async (config) => {
    requests.push(config.url!);
    throw expired(config);
  };
  const upload = apiClient.post('/documents/', { document: 'old' }, { ledovaSessionEpoch: epoch });
  const refused = expect(upload).rejects.toThrow('session changed');
  await blocked;
  const signingIn = storeTokens({ accessToken: 'new-access', refreshToken: 'new-refresh' });
  release();
  await Promise.all([signingIn, refused]);
  expect(requests).toEqual(blockedRead === 1 ? [] : ['/documents/']);
  await expect(getRefreshToken()).resolves.toBe('new-refresh');
});

it('retires a scope immediately even if queued sign-out storage fails', async () => {
  await storeTokens(pair);
  const epoch = getSessionEpoch();
  jest.mocked(SecureStore.setItemAsync).mockRejectedValue(new Error('storage unavailable'));
  const clearing = clearTokens();
  expect(getSessionEpoch()).not.toBe(epoch);
  await expect(clearing).rejects.toThrow('storage unavailable');
  const adapter = jest.fn<ReturnType<AxiosAdapter>, Parameters<AxiosAdapter>>();
  apiClient.defaults.adapter = adapter;
  await expect(apiClient.post('/documents/', {}, { ledovaSessionEpoch: epoch })).rejects.toThrow('session changed');
  expect(adapter).not.toHaveBeenCalled();
});
