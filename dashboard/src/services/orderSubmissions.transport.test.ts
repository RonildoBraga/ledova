import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, expect, it } from 'vitest';
import { AUTH_ENDPOINTS, OrderSubmission, TRADING_ENDPOINTS, createOrderSubmissionStore } from '@ledova/shared';
import apiClient from './apiClient';
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

const adapter = apiClient.defaults.adapter;
afterEach(() => {
  apiClient.defaults.adapter = adapter;
});

it.each([false, true])(
  'keeps a create identity and fences only a retired retry after CSRF refresh (retired=%s)',
  async (retired) => {
    const { storage } = memoryStorage();
    const store = createOrderSubmissionStore(storage, () => submissionId);
    const record = await store.create(owner, walletUuid);
    let current = true;
    const selection = new OrderSubmission(record, {
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
      if (config.url === TRADING_ENDPOINTS.ORDERS.CREATE_MESSAGE) return response(config, snapshot());
      if (sent.filter((c) => c.url === config.url).length === 1)
        throw new AxiosError(
          'CSRF',
          undefined,
          config,
          undefined,
          response(config, { detail: 'CSRF Failed: token missing.' }, 403),
        );
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
    }
  },
);
