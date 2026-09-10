import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { AUTH_ENDPOINTS, OrderAction, TRADING_ENDPOINTS, createOrderActionStore } from '@ledova/shared';
import { apiClient } from './apiClient';
import { clearTokens, storeTokens } from './tokenStorage';
import { getSessionEpoch } from './sessionScope';
import { deferred, memoryStorage, owner, response } from '../../../packages/shared/tests/fixtures/order-submissions';
import {
  actionContext,
  actionId,
  actionSnapshot,
  orderUuid,
} from '../../../packages/shared/tests/fixtures/order-actions';

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

it.each([false, true])(
  'keeps an action ID and fences a retired execute after bearer rotation (retired=%s)',
  async (retired) => {
    const { storage } = memoryStorage();
    const store = createOrderActionStore(storage, () => actionId);
    let current = true;
    const action = new OrderAction(owner, orderUuid, 'cancel', {
      apiClient,
      store,
      isCurrent: () => current,
      onSettled: () => {},
      onRecordsChanged: () => {},
      requestConfig: { ledovaSessionEpoch: getSessionEpoch() },
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
      if (config.url === TRADING_ENDPOINTS.ORDERS.ACTION_CONTEXT(orderUuid)) return response(config, actionContext());
      if (config.url === TRADING_ENDPOINTS.ORDERS.CANCEL_MESSAGE(orderUuid))
        return response(config, actionSnapshot('cancel'));
      if (sent.filter((request) => request.url === config.url).length === 1)
        throw new AxiosError('Expired', undefined, config, undefined, response(config, {}, 401));
      return response(config, actionSnapshot('cancel', 'applied'));
    };
    await action.load();
    await action.prepare();
    expect(action.getSnapshot().phase).toBe('ready');
    const posting = action.submitSignature('synthetic-signature');
    await started.promise;
    if (retired) current = false;
    refresh.resolve();
    await posting;
    const executes = sent.filter((request) => request.url === TRADING_ENDPOINTS.ORDERS.CANCEL(orderUuid));
    expect(executes).toHaveLength(retired ? 1 : 2);
    for (const request of executes) expect(JSON.parse(request.data).action_id).toBe(actionId);
    expect(await store.list(owner)).toHaveLength(retired ? 1 : 0);
    expect(
      sent
        .filter((request) => request.url?.includes('/trading/'))
        .every((request) => typeof request.ledovaSubmissionGuard === 'function'),
    ).toBe(true);
    if (retired) {
      expect((await apiClient.post('/ordinary/', {})).status).toBe(200);
      expect(sent.filter((request) => request.url === '/ordinary/')).toHaveLength(2);
    } else expect(executes[1]!.headers.Authorization).toBe('Bearer rotated-access');
  },
);
