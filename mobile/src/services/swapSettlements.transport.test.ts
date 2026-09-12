import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import { AUTH_ENDPOINTS, SwapSettlement, createSwapSettlementStore } from '@ledova/shared';
import { apiClient } from './apiClient';
import { clearTokens, storeTokens } from './tokenStorage';
import { getSessionEpoch } from './sessionScope';
import { swapSettlementCrypto } from './swapSettlements';
import { deferred, memoryStorage, response } from '../../../packages/shared/tests/fixtures/order-submissions';
import {
  settlementResponse,
  settlementOwner as owner,
  settlementFixture as fixture,
  settlementNow,
} from '../../../packages/shared/tests/fixtures/swap-settlements';

jest.mock('uuid', () => ({ v4: () => '70000000-0000-4000-8000-000000000001' }));
jest.mock('expo-secure-store', () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 7,
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));
const items = new Map<string, string>();
const initialAdapter = apiClient.defaults.adapter;
beforeEach(async () => {
  jest.spyOn(Date, 'now').mockReturnValue(settlementNow);
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
  'preserves the original settlement during auth refresh and fences retired replay (%s)',
  async (retired) => {
    const { storage } = memoryStorage();
    const store = createSwapSettlementStore(storage);
    const snapshot = settlementResponse();
    let current = true;
    const settlement = new SwapSettlement(owner, snapshot, {
      apiClient,
      store,
      crypto: swapSettlementCrypto,
      isCurrent: () => current,
      onUpdated: () => {},
      onRecordsChanged: () => {},
      requestConfig: { ledovaSessionEpoch: getSessionEpoch() },
    });
    const started = deferred<void>();
    const refreshed = deferred<void>();
    const sent: InternalAxiosRequestConfig[] = [];
    apiClient.defaults.adapter = async (config) => {
      sent.push(config);
      if (config.url === AUTH_ENDPOINTS.TOKEN_REFRESH) {
        started.resolve();
        await refreshed.promise;
        return response(config, { access: 'rotated-access', refresh: 'rotated-refresh' });
      }
      if (config.method === 'get') return response(config, snapshot);
      if (sent.filter((request) => request.url === config.url).length === 1)
        throw new AxiosError('Expired', undefined, config, undefined, response(config, {}, 401));
      snapshot.swapOrder.sellerHasSigned = true;
      snapshot.swapOrder.status = 'seller_signed';
      snapshot.hasSigned = true;
      snapshot.canSign = false;
      return response(config, snapshot.swapOrder);
    };
    await settlement.load();
    const posting = settlement.submitSignature(fixture.signatures[0], fixture.addresses[0]);
    await started.promise;
    if (retired) current = false;
    refreshed.resolve();
    await posting;
    const signed = sent.filter((request) => request.url?.endsWith('/sign/'));
    expect(signed).toHaveLength(retired ? 1 : 2);
    for (const request of signed)
      expect(JSON.parse(request.data)).toMatchObject({
        swap_uuid: snapshot.swapUuid,
        settlement_digest: snapshot.settlementDigest,
      });
    expect(await store.list(owner)).toHaveLength(retired ? 1 : 0);
    expect(
      sent
        .filter((request) => request.url?.includes('/trading/'))
        .every((request) => typeof request.ledovaSubmissionGuard === 'function'),
    ).toBe(true);
    if (retired) {
      expect((await apiClient.post('/ordinary/', {})).status).toBe(200);
      expect(sent.filter((request) => request.url === '/ordinary/')).toHaveLength(2);
    } else expect(signed[1].headers.Authorization).toBe('Bearer rotated-access');
  },
);
