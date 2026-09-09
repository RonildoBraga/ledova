import type { AxiosAdapter } from 'axios';
import { apiClient } from './apiClient';
import * as tokenStorage from './tokenStorage';

jest.mock('./tokenStorage', () => ({
  getAccessToken: jest.fn(async () => 'synthetic-access'),
  getRefreshToken: jest.fn(),
  storeTokens: jest.fn(),
  clearTokens: jest.fn(),
}));

const adapter = jest.fn<ReturnType<AxiosAdapter>, Parameters<AxiosAdapter>>(async (config) => ({
  data: {},
  status: 200,
  statusText: 'OK',
  headers: {},
  config,
}));

beforeEach(() => {
  process.env.EXPO_PUBLIC_API_URL = 'https://api.example.test';
  apiClient.defaults.baseURL = process.env.EXPO_PUBLIC_API_URL;
  apiClient.defaults.adapter = adapter;
  jest.mocked(tokenStorage.getAccessToken).mockResolvedValue('synthetic-access');
});

it('removes an existing bearer header when the stored session is absent', async () => {
  jest.mocked(tokenStorage.getAccessToken).mockResolvedValue(null);
  await apiClient.get('/api/v1/wallets/', { headers: { authorization: 'Bearer stale-synthetic-access' } });
  expect(adapter).toHaveBeenCalledTimes(1);
  expect(adapter.mock.calls[0][0].headers.has('Authorization')).toBe(false);
});

it('sends a bearer token to a relative API route and its same-origin authenticated download', async () => {
  await apiClient.get('/api/v1/wallets/');
  await apiClient.get('https://api.example.test/api/v1/documents/synthetic/file/');
  expect(adapter).toHaveBeenCalledTimes(2);
  expect(adapter.mock.calls[0][0].headers.Authorization).toBe('Bearer synthetic-access');
});

it.each([
  ['absolute HTTP', { url: 'http://api.example.test/api/v1/wallets/' }],
  ['absolute foreign HTTPS', { url: 'https://foreign.example.test/api/v1/wallets/' }],
  ['protocol relative', { url: '//foreign.example.test/api/v1/wallets/' }],
  ['base URL override', { url: '/api/v1/wallets/', baseURL: 'https://foreign.example.test' }],
  ['embedded credentials', { url: 'https://user:password@api.example.test/api/v1/wallets/' }],
])('refuses %s before reading or sending a bearer token', async (_name, config) => {
  await expect(apiClient.request(config)).rejects.toThrow();
  expect(tokenStorage.getAccessToken).not.toHaveBeenCalled();
  expect(adapter).not.toHaveBeenCalled();
});
