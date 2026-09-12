import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, expect, it } from 'vitest';
import { AUTH_ENDPOINTS, OrderAction, TRADING_ENDPOINTS, createOrderActionStore } from '@ledova/shared';
import apiClient from './apiClient';
import { deferred, memoryStorage, owner, response } from '../../../packages/shared/tests/fixtures/order-submissions';
import {
  actionContext,
  actionId,
  actionSnapshot,
  orderUuid,
} from '../../../packages/shared/tests/fixtures/order-actions';

const adapter = apiClient.defaults.adapter;
afterEach(() => {
  apiClient.defaults.adapter = adapter;
});

it.each([false, true])(
  'keeps an action ID and fences a retired execute after CSRF refresh (retired=%s)',
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
    });
    const started = deferred<void>();
    const refresh = deferred<void>();
    const sent: InternalAxiosRequestConfig[] = [];
    apiClient.defaults.adapter = async (config) => {
      sent.push(config);
      if (config.url === AUTH_ENDPOINTS.VERIFY) {
        started.resolve();
        await refresh.promise;
        return response(config, { valid: true });
      }
      if (config.url === TRADING_ENDPOINTS.ORDERS.ACTION_CONTEXT(orderUuid)) return response(config, actionContext());
      if (config.url === TRADING_ENDPOINTS.ORDERS.CANCEL_MESSAGE(orderUuid))
        return response(config, actionSnapshot('cancel'));
      if (sent.filter((request) => request.url === config.url).length === 1)
        throw new AxiosError(
          'CSRF',
          undefined,
          config,
          undefined,
          response(config, { detail: 'CSRF Failed: token missing.' }, 403),
        );
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
    }
  },
);
