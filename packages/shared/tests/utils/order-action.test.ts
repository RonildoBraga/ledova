import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { TRADING_ENDPOINTS } from '../../src/constants';
import { OrderAction } from '../../src/utils/order-action';
import { createOrderActionStore } from '../../src/utils/order-action-storage';
import type { OrderActionContext, OrderActionPurpose, OrderActionSnapshot } from '../../src/types';
import {
  actionContext,
  actionId,
  actionSnapshot,
  largeMinimum,
  largeQuantity,
  orderUuid,
  otherActionId,
} from '../fixtures/order-actions';
import { deferred, memoryStorage, owner, otherAccountUuid, response } from '../fixtures/order-submissions';

const endpoints = TRADING_ENDPOINTS.ORDERS;

function setup(purpose: OrderActionPurpose = 'modify', context = actionContext()) {
  const { storage, values } = memoryStorage();
  let nextId = actionId;
  const store = createOrderActionStore(storage, () => {
    const id = nextId;
    nextId = otherActionId;
    return id;
  });
  const api = axios.create();
  let current = true;
  const requests: InternalAxiosRequestConfig[] = [];
  let handler = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
    if (config.url === endpoints.ACTION_CONTEXT(orderUuid)) return response(config, context);
    const status = config.url?.endsWith('/message/') || config.method === 'get' ? 'pending' : 'applied';
    const snapshot = actionSnapshot(purpose, status, context);
    if (config.method === 'get') snapshot.challenge = null;
    return response(config, snapshot);
  };
  api.defaults.adapter = async (config) => {
    config.ledovaSubmissionGuard?.();
    requests.push(config);
    const reply = await handler(config);
    return { ...reply, data: JSON.stringify(reply.data) };
  };
  const settled = jest.fn();
  const changed = jest.fn();
  const dependencies = {
    apiClient: api,
    store,
    isCurrent: () => current,
    onSettled: settled,
    onRecordsChanged: changed,
  };
  const action = new OrderAction(owner, orderUuid, purpose, dependencies);
  return {
    action,
    api,
    requests,
    values,
    storage,
    store,
    settled,
    changed,
    context,
    dependencies,
    handler: (replacement: typeof handler) => {
      handler = replacement;
    },
    retire: () => {
      current = false;
    },
  };
}

async function prepare(f: ReturnType<typeof setup>) {
  await f.action.load();
  f.action.edit('pricePerShare', '14.00');
  await f.action.prepare();
  expect(f.action.getSnapshot().phase).toBe('ready');
}

function fail(config: InternalAxiosRequestConfig, data: unknown, status: number): never {
  throw new AxiosError('Synthetic refused response', String(status), config, undefined, response(config, data, status));
}

test('first price-only edit uses exact parsed context values and persists IDs before message HTTP', async () => {
  const f = setup('modify', actionContext(largeQuantity, largeMinimum));
  f.handler(async (config) => {
    if (config.url === endpoints.ACTION_CONTEXT(orderUuid)) {
      expect(f.values.size).toBe(0);
      return response(config, f.context);
    }
    expect([...f.values.values()].map((value) => JSON.parse(value))).toEqual([
      {
        version: 1,
        ...owner,
        orderUuid,
        purpose: 'modify',
        actionId,
      },
    ]);
    const body = JSON.parse(config.data);
    expect(body).toEqual({
      action_id: actionId,
      owner_account_uuid: owner.ownerAccountUuid,
      new_quantity: largeQuantity,
      new_min_quantity: largeMinimum,
      new_price_per_share: '14.00',
    });
    return response(config, actionSnapshot('modify', 'pending', f.context));
  });
  await prepare(f);
  expect(f.action.getSnapshot().challenge?.message.newQuantity).toBe(largeQuantity);
  expect(f.requests.map((request) => request.method)).toEqual(['get', 'post']);
});

test.each(['cancel', 'modify'] as const)(
  'lost %s response recovers the original result without a second execution or context',
  async (purpose) => {
    const f = setup(purpose);
    await prepare(f);
    f.handler(async (config) => {
      if (config.method === 'post') throw new Error('Synthetic lost response after commit');
      return response(config, actionSnapshot(purpose, 'applied'));
    });
    await f.action.sign(async () => 'synthetic signature');
    expect(f.action.getSnapshot().phase).toBe('error');
    expect(f.values.size).toBe(1);
    const record = (await f.store.list(owner))[0]!;
    f.action.close();
    const recovered = new OrderAction(owner, orderUuid, purpose, f.dependencies, record);
    const before = f.requests.length;
    await recovered.recover();
    expect(f.requests.slice(before).map((request) => [request.method, request.url])).toEqual([
      ['get', endpoints.ACTION(actionId)],
    ]);
    expect(recovered.getSnapshot().phase).toBe('applied');
    expect(recovered.getSnapshot().snapshot?.order.pricePerShare).toBe('15.00');
    expect(f.settled).toHaveBeenCalledTimes(1);
    expect(f.values.size).toBe(0);
  },
);

test('pending restart forwards the immutable exact replacements through a same-ID message', async () => {
  const f = setup('modify', actionContext(largeQuantity, largeMinimum));
  await prepare(f);
  const record = (await f.store.list(owner))[0]!;
  const recovered = new OrderAction(owner, orderUuid, 'modify', f.dependencies, record);
  f.requests.length = 0;
  await recovered.recover();
  expect(f.requests.map((request) => request.url)).toEqual([
    endpoints.ACTION(actionId),
    endpoints.MODIFY_MESSAGE(orderUuid),
  ]);
  expect(JSON.parse(f.requests[1]!.data)).toEqual({
    action_id: actionId,
    owner_account_uuid: owner.ownerAccountUuid,
    new_quantity: largeQuantity,
    new_min_quantity: largeMinimum,
    new_price_per_share: '14.00',
  });
  expect(recovered.getSnapshot().phase).toBe('ready');
});

test.each(['cancel', 'modify'] as const)(
  'validated stored %s refusal resolves the reminder on its original HTTP status',
  async (purpose) => {
    const f = setup(purpose);
    await prepare(f);
    f.handler(async (config) => {
      const snapshot = actionSnapshot(purpose, 'refused');
      return fail(config, snapshot, snapshot.refusal!.httpStatus);
    });
    await f.action.sign(async () => 'synthetic signature');
    expect(f.action.getSnapshot().phase).toBe('refused');
    expect(f.values.size).toBe(0);
    expect(f.settled).toHaveBeenCalledTimes(1);
  },
);

test.each(['action_intent_conflict', 'action_context_conflict'])('ordinary %s 409 remains unresolved', async (code) => {
  const f = setup();
  await prepare(f);
  f.handler(async (config) => fail(config, { code, detail: 'The action conflicts with current context.' }, 409));
  await f.action.sign(async () => 'synthetic signature');
  expect(f.action.getSnapshot().phase).toBe('error');
  expect(f.values.size).toBe(1);
  expect(f.settled).not.toHaveBeenCalled();
});

test.each<[string, (snapshot: OrderActionSnapshot) => void]>([
  [
    'another action ID',
    (s) => {
      s.actionId = otherActionId;
    },
  ],
  [
    'another owner account',
    (s) => {
      s.ownerAccountUuid = otherAccountUuid;
    },
  ],
  [
    'another purpose',
    (s) => {
      s.purpose = 'cancel';
    },
  ],
  [
    'mismatched HTTP status',
    (s) => {
      s.refusal!.httpStatus = 400;
    },
  ],
  [
    'ordinary conflict code',
    (s) => {
      s.refusal!.code = 'action_context_conflict';
    },
  ],
  [
    'empty refusal detail',
    (s) => {
      s.refusal!.detail = '';
    },
  ],
  [
    'unexpected applied result',
    (s) => {
      s.result = { kind: 'cancel', fromStatus: 'open', toStatus: 'cancelled' };
    },
  ],
  [
    'unexpected challenge',
    (s) => {
      s.challenge = actionSnapshot().challenge;
    },
  ],
  [
    'changed immutable quantity',
    (s) => {
      s.intent.modifications!.quantity = '11';
    },
  ],
])('malformed or mismatched refused envelope with %s cannot clear a reminder', async (_name, change) => {
  const f = setup();
  await prepare(f);
  f.handler(async (config) => {
    const snapshot = actionSnapshot('modify', 'refused');
    change(snapshot);
    return fail(config, snapshot, 409);
  });
  await f.action.sign(async () => 'synthetic signature');
  expect(f.action.getSnapshot().phase).toBe('error');
  expect(f.values.size).toBe(1);
  expect(f.settled).not.toHaveBeenCalled();
});

test('context identity change during first issuance retires review and recovers the same action for fresh review', async () => {
  const f = setup();
  await f.action.load();
  f.action.edit('pricePerShare', '14.00');
  const changed = { ...f.context, walletUuid: '30000000-0000-4000-8000-000000000009' };
  f.handler(async (config) => {
    const data = actionSnapshot('modify', 'pending', changed);
    if (config.method === 'get') data.challenge = null;
    return response(config, data);
  });
  await f.action.prepare();
  expect(f.action.getSnapshot().phase).toBe('error');
  expect(f.action.getSnapshot().challenge).toBeNull();
  expect(f.values.size).toBe(1);
  const signer = jest.fn(async () => 'synthetic');
  await f.action.sign(signer);
  expect(signer).not.toHaveBeenCalled();
  await f.action.recover();
  expect(f.action.record?.actionId).toBe(actionId);
  expect(f.action.getSnapshot().phase).toBe('ready');
  expect(f.action.getSnapshot().snapshot?.walletUuid).toBe(changed.walletUuid);
});

test('storage write/readback failure prevents HTTP and can retry persistence with the same reserved ID', async () => {
  const f = setup();
  await f.action.load();
  f.action.edit('pricePerShare', '14.00');
  const get = f.storage.getItem;
  let saved = false;
  const set = f.storage.setItem;
  f.storage.setItem = async (key, value) => {
    await set(key, value);
    saved = true;
  };
  f.storage.getItem = (key) => {
    if (saved) throw new Error('Synthetic readback failure');
    return get(key);
  };
  await f.action.prepare();
  expect(f.requests).toHaveLength(1);
  expect(f.action.record?.actionId).toBe(actionId);
  f.storage.getItem = get;
  await f.action.recover();
  expect(f.action.getSnapshot().phase).toBe('ready');
  expect(f.action.record?.actionId).toBe(actionId);
});

test('retirement during persistence prevents a late first message, with a live positive control', async () => {
  const f = setup();
  await f.action.load();
  f.action.edit('pricePerShare', '14.00');
  const pause = deferred<void>();
  const set = f.storage.setItem;
  f.storage.setItem = async (key, value) => {
    await pause.promise;
    await set(key, value);
  };
  const pending = f.action.prepare();
  f.retire();
  pause.resolve();
  await pending;
  expect(f.requests).toHaveLength(1);
  expect(f.values.size).toBe(1);
  const positive = setup();
  await prepare(positive);
  expect(positive.requests).toHaveLength(2);
});

test('a 404 reminder lookup stays unresolved and never fetches fresh context', async () => {
  const f = setup();
  const record = f.store.reserve(owner, orderUuid, 'modify');
  await f.store.persist(record);
  f.handler(async (config) => fail(config, { detail: 'Not found.' }, 404));
  const recovered = new OrderAction(owner, orderUuid, 'modify', f.dependencies, record);
  await recovered.recover();
  expect(f.requests.map((request) => request.url)).toEqual([endpoints.ACTION(actionId)]);
  expect(recovered.getSnapshot().phase).toBe('error');
  expect(f.values.size).toBe(1);
});

test('an already present action ID cannot be adopted by a new reservation after a collision', async () => {
  const { storage, values } = memoryStorage();
  const store = createOrderActionStore(storage, () => actionId);
  const original = store.reserve(owner, orderUuid, 'cancel');
  await store.persist(original);
  const colliding = store.reserve(owner, orderUuid, 'cancel');
  await expect(store.persist(colliding)).rejects.toThrow('already exists');
  await expect(store.persist(colliding, true)).rejects.toThrow('already exists');
  expect(values.size).toBe(1);
  await expect(store.persist(original, true)).resolves.toBeUndefined();
});

test('field validation details remain visible without becoming a stored refusal', async () => {
  const f = setup();
  await prepare(f);
  f.handler(async (config) => fail(config, { new_quantity: ['New quantity must exceed the filled amount.'] }, 400));
  await f.action.sign(async () => 'synthetic signature');
  expect(f.action.getSnapshot().error).toBe('New quantity must exceed the filled amount.');
  expect(f.values.size).toBe(1);
  expect(f.action.getSnapshot().canRemoveReminder).toBe(false);
  await f.action.removeReminder();
  expect(f.values.size).toBe(1);
  expect(f.settled).not.toHaveBeenCalled();
});

async function rejectedPreparation(f: ReturnType<typeof setup>) {
  await f.action.load();
  f.handler(async (config) => fail(config, { detail: 'The requested change is no longer valid.' }, 400));
  await f.action.prepare();
  expect(f.action.getSnapshot()).toMatchObject({ phase: 'error', canRemoveReminder: true });
  expect(f.values.size).toBe(1);
}

test.each(['cancel', 'modify'] as const)(
  'a rejected %s preparation keeps its reminder until explicit removal',
  async (purpose) => {
    const f = setup(purpose);
    await rejectedPreparation(f);
    const original = f.action.record;
    const refreshed = actionContext('15', '3');
    f.handler(async (config) => response(config, refreshed));
    const before = f.requests.length;
    await f.action.removeReminder();
    expect(f.values.size).toBe(0);
    expect(f.action.record).toBeNull();
    expect(f.action.getSnapshot()).toMatchObject({
      phase: 'editing',
      canRemoveReminder: false,
      context: refreshed,
      values: { quantity: '15', minQuantity: '3', pricePerShare: '12.50' },
      snapshot: null,
      challenge: null,
    });
    expect(f.requests.slice(before).map((config) => [config.method, config.url])).toEqual([
      ['get', endpoints.ACTION_CONTEXT(orderUuid)],
    ]);
    expect(f.settled).not.toHaveBeenCalled();
    f.handler(async (config) => {
      const body = JSON.parse(config.data);
      return response(
        config,
        actionSnapshot(purpose, 'pending', refreshed, f.action.getSnapshot().values!, body.action_id),
      );
    });
    await f.action.prepare();
    expect(f.action.getSnapshot().phase).toBe('ready');
    expect(f.action.record?.actionId).toBe(otherActionId);
    expect(f.action.record?.actionId).not.toBe(original?.actionId);
    expect(f.values.size).toBe(1);
  },
);

test.each(['lost response', 'server error', 'conflict', 'another endpoint'])(
  '%s during preparation does not enable removal of an unresolved reminder',
  async (failure) => {
    const f = setup();
    await f.action.load();
    f.handler(async (config) => {
      if (failure === 'lost response') throw new Error('Synthetic lost response');
      if (failure === 'another endpoint')
        return fail({ ...config, url: '/api/token/refresh/' }, { detail: 'Synthetic refresh rejection.' }, 400);
      return fail(config, { detail: 'The result is unavailable.' }, failure === 'conflict' ? 409 : 500);
    });
    await f.action.prepare();
    expect(f.action.getSnapshot()).toMatchObject({ phase: 'error', canRemoveReminder: false });
    const before = f.requests.length;
    await f.action.removeReminder();
    expect(f.values.size).toBe(1);
    expect(f.requests).toHaveLength(before);
    expect(f.settled).not.toHaveBeenCalled();
  },
);

test('a failed reminder removal remains retryable and cannot start a replacement', async () => {
  const f = setup();
  await rejectedPreparation(f);
  const original = f.action.record;
  const remove = f.storage.removeItem;
  f.storage.removeItem = () => {};
  const before = f.requests.length;
  await f.action.removeReminder();
  expect(f.action.getSnapshot()).toMatchObject({ phase: 'error', canRemoveReminder: true });
  expect(f.action.record).toBe(original);
  expect(f.values.size).toBe(1);
  await f.action.prepare();
  expect(f.requests).toHaveLength(before);
  f.storage.removeItem = remove;
  f.handler(async (config) => response(config, f.context));
  await f.action.removeReminder();
  expect(f.action.getSnapshot().phase).toBe('editing');
  expect(f.values.size).toBe(0);
});

test('failure to reload current order after removal cannot reuse the old context or action', async () => {
  const f = setup();
  await rejectedPreparation(f);
  f.handler(async (config) => fail(config, { detail: 'The order is temporarily unavailable.' }, 503));
  await f.action.removeReminder();
  expect(f.values.size).toBe(0);
  expect(f.action.record).toBeNull();
  expect(f.action.getSnapshot()).toMatchObject({
    phase: 'error',
    context: null,
    values: null,
    canRemoveReminder: false,
  });
  const before = f.requests.length;
  await f.action.prepare();
  expect(f.requests).toHaveLength(before);
  f.handler(async (config) => response(config, actionContext('20', '4')));
  await f.action.recover();
  expect(f.action.getSnapshot()).toMatchObject({ phase: 'editing', values: { quantity: '20', minQuantity: '4' } });
});

test('a subsequent uncertain recovery revokes the earlier reminder-removal option', async () => {
  const f = setup();
  await rejectedPreparation(f);
  f.handler(async (config) => fail(config, { detail: 'Action not found.' }, 404));
  await f.action.recover();
  expect(f.action.getSnapshot()).toMatchObject({ phase: 'error', canRemoveReminder: false });
  await f.action.removeReminder();
  expect(f.values.size).toBe(1);
});

test.each(['close', 'account change'])('%s retires the reminder-removal control', async (retire) => {
  const f = setup();
  await rejectedPreparation(f);
  if (retire === 'close') f.action.close();
  else f.retire();
  const before = f.requests.length;
  await f.action.removeReminder();
  expect(f.values.size).toBe(1);
  expect(f.requests).toHaveLength(before);
});

test('no-change modification remains a recorded result distinct from later current order fields', async () => {
  const f = setup();
  await prepare(f);
  f.handler(async (config) => {
    const snapshot = actionSnapshot('modify', 'applied');
    snapshot.result = { kind: 'modify', modificationCount: 3, changes: [] };
    return response(config, snapshot);
  });
  await f.action.sign(async () => 'synthetic signature');
  expect(f.action.getSnapshot().snapshot?.result).toEqual({ kind: 'modify', modificationCount: 3, changes: [] });
  expect(f.action.getSnapshot().snapshot?.order.pricePerShare).toBe('15.00');
  expect(f.values.size).toBe(0);
});

test('duplicate preparation and signature presses submit once; late signer completion cannot send after close', async () => {
  const f = setup();
  await f.action.load();
  f.action.edit('pricePerShare', '14.00');
  await Promise.all([f.action.prepare(), f.action.prepare()]);
  expect(f.requests).toHaveLength(2);
  const pause = deferred<string>();
  const signer = jest.fn(() => pause.promise);
  const first = f.action.sign(signer);
  await f.action.sign(signer);
  f.action.close();
  pause.resolve('synthetic signature');
  await first;
  expect(signer).toHaveBeenCalledTimes(1);
  expect(f.requests).toHaveLength(2);
  expect(f.values.size).toBe(1);
  const positive = setup();
  await prepare(positive);
  await positive.action.sign(async () => 'synthetic signature');
  expect(positive.action.getSnapshot().phase).toBe('applied');
});

test.each([
  (context: OrderActionContext) => {
    context.currentValues.quantity = Number(largeQuantity) as unknown as string;
  },
  (context: OrderActionContext) => {
    context.ownerAccountUuid = otherAccountUuid;
  },
])('invalid or foreign initial context %p cannot issue an action', async (mutate) => {
  const context = actionContext();
  mutate(context);
  const f = setup('modify', context);
  await f.action.load();
  await f.action.prepare();
  expect(f.action.getSnapshot().phase).toBe('error');
  expect(f.requests).toHaveLength(1);
  expect(f.values.size).toBe(0);
});

test('expired signing recovers the original applied action without invoking a new signer', async () => {
  const f = setup();
  await prepare(f);
  const expiry = Date.parse(f.action.getSnapshot().challenge!.expiresAt);
  const now = jest.spyOn(Date, 'now').mockReturnValue(expiry + 1);
  try {
    f.handler(async (config) => response(config, actionSnapshot('modify', 'applied')));
    const count = f.requests.length;
    const signer = jest.fn();
    await f.action.sign(signer);
    expect(signer).not.toHaveBeenCalled();
    expect(f.action.getSnapshot().phase).toBe('applied');
    expect(f.requests.slice(count).map((config) => [config.method, config.url])).toEqual([
      ['get', endpoints.ACTION(actionId)],
    ]);
    expect(f.values.size).toBe(0);
  } finally {
    now.mockRestore();
  }
});

test('recovery compares a recorded outcome by values and rejects a changed original result', async () => {
  const f = setup('cancel');
  await f.action.load();
  await f.action.prepare();
  await f.action.submitSignature('synthetic-signature');
  expect(f.action.getSnapshot().phase).toBe('applied');
  const same = actionSnapshot('cancel', 'applied');
  same.result = { toStatus: 'cancelled', fromStatus: 'open', kind: 'cancel' };
  f.handler(async (config) => response(config, same));
  await f.action.recover();
  expect(f.action.getSnapshot().phase).toBe('applied');
  same.result = { toStatus: 'cancelled', fromStatus: 'matched', kind: 'cancel' };
  await f.action.recover();
  expect(f.action.getSnapshot().phase).toBe('error');
  expect(f.action.getSnapshot().error).toContain('changed its recorded outcome');
});

test.each(['executing', 'failed'])('recovers an original result when the current order is later %s', async (status) => {
  const f = setup();
  await prepare(f);
  f.handler(async () => {
    throw new Error('Synthetic lost committed response');
  });
  await f.action.submitSignature('synthetic-signature');
  expect(f.action.getSnapshot().phase).toBe('error');
  expect(f.values.size).toBe(1);
  const original = actionSnapshot('modify', 'applied');
  Object.assign(original.order, { status });
  f.handler(async (config) => response(config, original));
  const count = f.requests.length;
  await f.action.recover();
  expect(f.action.getSnapshot().phase).toBe('applied');
  expect(f.action.getSnapshot().snapshot?.result).toEqual(original.result);
  expect(f.action.getSnapshot().snapshot?.order.status).toBe(status);
  expect(f.requests.slice(count).map((request) => [request.method, request.url])).toEqual([
    ['get', endpoints.ACTION(actionId)],
  ]);
  expect(f.values.size).toBe(0);
});
