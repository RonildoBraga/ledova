import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { AUTH_ENDPOINTS, OrderSubmission, TRADING_ENDPOINTS, createOrderSubmissionStore } from '@ledova/shared';
import { apiClient } from './apiClient';
import { clearTokens, storeTokens } from './tokenStorage';
import { getSessionEpoch } from './sessionScope';
import {
  deferred,
  draft,
  memoryStorage,
  owner,
  response,
  snapshot,
  submissionId,
  walletUuid,
} from '../../../packages/shared/tests/fixtures/order-submissions';

jest.mock('expo-secure-store', () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 7,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));
const items = new Map<string, string>();
const initialAdapter = apiClient.defaults.adapter;
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
  await storeTokens({ accessToken: 'synthetic-access', refreshToken: 'synthetic-refresh' });
  process.env.EXPO_PUBLIC_API_URL = 'https://api.example.test';
  apiClient.defaults.baseURL = process.env.EXPO_PUBLIC_API_URL;
});
afterEach(() => {
  apiClient.defaults.adapter = initialAdapter;
});

it.each([false, true])('keeps the ID and checks the view after bearer rotation (retired=%s)', async (retired) => {
  const { storage } = memoryStorage();
  const store = createOrderSubmissionStore(storage, () => submissionId);
  const record = await store.create(owner, walletUuid);
  let current = true;
  const selection = new OrderSubmission(record, {
    apiClient,
    store,
    requestConfig: { ledovaSessionEpoch: getSessionEpoch() },
    isCurrent: () => current,
    onSettled: () => {},
    onRecordsChanged: () => {},
  });
  const started = deferred<void>();
  const refresh = deferred<void>();
  const sent: InternalAxiosRequestConfig[] = [];
  apiClient.defaults.adapter = async (config) => {
    sent.push(config);
    if (config.url === AUTH_ENDPOINTS.TOKEN_REFRESH) {
      started.resolve();
      await refresh.promise;
      return response(config, { access: 'rotated-access', refresh: 'rotated-refresh' });
    }
    if (config.url === TRADING_ENDPOINTS.ORDERS.CREATE_MESSAGE) return response(config, snapshot());
    if (sent.filter((c) => c.url === config.url).length === 1)
      throw new AxiosError('Expired', undefined, config, undefined, response(config, {}, 401));
    return response(config, snapshot(submissionId, 'created'), 201);
  };
  await selection.start(draft);
  const posting = selection.submitSignature('synthetic-signature');
  await started.promise;
  if (retired) current = false;
  refresh.resolve();
  await posting;
  const creates = sent.filter((c) => c.url === TRADING_ENDPOINTS.ORDERS.CREATE);
  expect(creates).toHaveLength(retired ? 1 : 2);
  for (const request of creates) expect(JSON.parse(request.data).submission_id).toBe(submissionId);
  expect(await store.list(owner)).toHaveLength(retired ? 1 : 0);
  if (retired) {
    const ordinary = await apiClient.post('/ordinary/', {});
    expect(ordinary.status).toBe(201);
    expect(sent.filter((c) => c.url === '/ordinary/')).toHaveLength(2);
  } else expect(creates[1].headers.Authorization).toBe('Bearer rotated-access');
});
