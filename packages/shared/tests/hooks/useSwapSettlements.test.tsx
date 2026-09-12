/** @jest-environment jsdom */
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import type { ReactNode } from 'react';
import { ApiClientProvider } from '../../src/hooks/useApiClient';
import { AUTH_QUERY_KEY } from '../../src/hooks/useAuth';
import { USER_PREFERENCES_QUERY_KEY } from '../../src/hooks/useUserPreferences';
import { useSwapSettlements } from '../../src/hooks/useSwapSettlements';
import { useOrderActions } from '../../src/hooks/useOrderActions';
import { useOrderSubmissions, type OrderSubmissionSession } from '../../src/hooks/useOrderSubmissions';
import { createOrderActionStore } from '../../src/utils/order-action-storage';
import { createOrderSubmissionStore } from '../../src/utils/order-submission-storage';
import { createSwapSettlementStore } from '../../src/utils/swap-settlement-storage';
import { swapSettlementIdentity } from '../../src/utils/swap-settlement-validation';
import { deferred, memoryStorage, response as reply } from '../fixtures/order-submissions';
import { settlementCrypto, settlementNow, settlementOwner, settlementResponse } from '../fixtures/swap-settlements';

const clients: QueryClient[] = [];
function setup() {
  const query = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: Infinity } },
  });
  clients.push(query);
  const preferences = {
    data: { userProfile: settlementOwner.userUuid, selectedAccount: { uuid: settlementOwner.ownerAccountUuid } },
  };
  query.setQueryData(AUTH_QUERY_KEY, { data: { valid: true } });
  query.setQueryData(USER_PREFERENCES_QUERY_KEY, preferences);
  const api = axios.create();
  const requests: InternalAxiosRequestConfig[] = [];
  let handler = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> =>
    reply(config, settlementResponse());
  api.interceptors.request.use((config) => {
    config.ledovaSubmissionGuard?.();
    return config;
  });
  api.defaults.adapter = async (config) => {
    requests.push(config);
    return handler(config);
  };
  const { storage } = memoryStorage();
  const store = createSwapSettlementStore(storage);
  const crypto = settlementCrypto();
  let epoch = 0;
  const listeners = new Set<() => void>();
  const session: OrderSubmissionSession = {
    getEpoch: () => epoch,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    requestConfig: () => ({ headers: { 'X-Test-Epoch': String(epoch) } }),
  };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={query}>
      <ApiClientProvider client={api}>{children}</ApiClientProvider>
    </QueryClientProvider>
  );
  return {
    query,
    api,
    requests,
    store,
    storage,
    crypto,
    session,
    wrapper,
    preferences,
    handle: (next: typeof handler) => {
      handler = next;
    },
    nextEpoch: () => {
      epoch++;
      for (const listener of [...listeners]) listener();
    },
  };
}

beforeEach(() => {
  jest.spyOn(Date, 'now').mockReturnValue(settlementNow);
});
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  jest.restoreAllMocks();
});

test('late A context cannot replace B after selection or unmount', async () => {
  const f = setup();
  const held = deferred<AxiosResponse>();
  const firstRequest = deferred<InternalAxiosRequestConfig>();
  const a = settlementResponse();
  const b = settlementResponse();
  b.swapUuid = b.swapOrder.uuid = b.swapOrder.settlementContext.swapUuid = '30000000-0000-4000-8000-000000000099';
  f.handle(async (config) => {
    if (config.params.swap_uuid === a.swapUuid) {
      firstRequest.resolve(config);
      return held.promise;
    }
    return reply(config, b);
  });
  const { result, unmount } = renderHook(() => useSwapSettlements(f.store, f.crypto, f.session), {
    wrapper: f.wrapper,
  });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  let first: ReturnType<typeof result.current.open> = null;
  act(() => {
    first = result.current.open(swapSettlementIdentity(a));
  });
  const request = await firstRequest.promise;
  act(() => {
    result.current.open(swapSettlementIdentity(b));
  });
  await waitFor(() => expect(result.current.active?.getSnapshot().response?.swapUuid).toBe(b.swapUuid));
  await act(async () => {
    held.resolve(reply(request, a));
  });
  expect(first!.isCurrent()).toBe(false);
  expect(first!.getSnapshot().response).toBeNull();
  expect(result.current.active!.getSnapshot().response!.swapUuid).toBe(b.swapUuid);
  const second = result.current.active!;
  unmount();
  expect(second.isCurrent()).toBe(false);
});

test.each(['account', 'session', 'logout', 'wallet'] as const)(
  '%s changes retire transport synchronously before a React commit',
  async (change) => {
    const f = setup();
    let walletCurrent = true;
    const { result } = renderHook(() => useSwapSettlements(f.store, f.crypto, f.session), { wrapper: f.wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.open(swapSettlementIdentity(settlementResponse()), () => walletCurrent);
    });
    await waitFor(() => expect(result.current.active!.getSnapshot().response).not.toBeNull());
    const active = result.current.active!;
    const request = f.requests.find((item) => item.url?.includes('/swap/'))!;
    act(() => {
      if (change === 'account')
        f.query.setQueryData(USER_PREFERENCES_QUERY_KEY, {
          data: { ...f.preferences.data, selectedAccount: { uuid: '20000000-0000-4000-8000-000000000099' } },
        });
      if (change === 'session') f.nextEpoch();
      if (change === 'logout') f.query.setQueryData(AUTH_QUERY_KEY, { data: { valid: false } });
      if (change === 'wallet') walletCurrent = false;
      expect(active.isCurrent()).toBe(false);
      expect(() => request.ledovaSubmissionGuard!()).toThrow(/no longer active/);
    });
  },
);

test('nonidentity preference updates preserve the live owner while epoch changes retire all three existing owner consumers', async () => {
  const f = setup();
  const actions = createOrderActionStore(f.storage, () => '40000000-0000-4000-8000-000000000099');
  const submissions = createOrderSubmissionStore(f.storage, () => '50000000-0000-4000-8000-000000000099');
  const { result } = renderHook(
    () => ({
      settlements: useSwapSettlements(f.store, f.crypto, f.session),
      actions: useOrderActions(actions, f.session),
      submissions: useOrderSubmissions(submissions, f.session),
    }),
    { wrapper: f.wrapper },
  );
  await waitFor(() => expect(result.current.settlements.isLoading).toBe(false));
  const original = {
    settlement: result.current.settlements.owner,
    action: result.current.actions.owner,
    submission: result.current.submissions.owner,
  };
  act(() => {
    f.query.setQueryData(USER_PREFERENCES_QUERY_KEY, { data: { ...f.preferences.data, currency: 'USD' } });
  });
  expect(result.current.settlements.owner).toBe(original.settlement);
  expect(result.current.actions.owner).toBe(original.action);
  expect(result.current.submissions.owner).toBe(original.submission);
  act(() => {
    f.nextEpoch();
  });
  expect(result.current.settlements.owner).not.toBe(original.settlement);
  expect(result.current.actions.owner).not.toBe(original.action);
  expect(result.current.submissions.owner).not.toBe(original.submission);
  expect(result.current.settlements.owner).toEqual(settlementOwner);
});
