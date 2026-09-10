import axios, { AxiosError } from 'axios';
import type { AxiosResponse } from 'axios';
import { createOrderSubmissionStore } from '../../src/utils/order-submission-storage';
import { OrderSubmission } from '../../src/utils/order-submission';
import { createOrder, getOrderCreateMessage, getOrderSubmission } from '../../src/services/trading';
import { TRADING_ENDPOINTS } from '../../src/constants/business/trading';
import {
  accountUuid,
  deferred,
  draft,
  memoryStorage,
  otherAccountUuid,
  owner,
  response,
  secondId,
  snapshot,
  submissionId,
  walletUuid,
} from '../fixtures/order-submissions';

const endpoints = TRADING_ENDPOINTS.ORDERS;

async function setup() {
  const memory = memoryStorage();
  const newUuid = jest.fn(() => submissionId);
  const store = createOrderSubmissionStore(memory.storage, newUuid);
  const record = await store.create(owner, walletUuid);
  const client = axios.create();
  let active = true;
  const settled = jest.fn();
  const changed = jest.fn();
  const make = () =>
    new OrderSubmission(record, {
      apiClient: client,
      store,
      isCurrent: () => active,
      onSettled: settled,
      onRecordsChanged: changed,
    });
  return {
    ...memory,
    newUuid,
    store,
    record,
    client,
    settled,
    changed,
    selection: make(),
    make,
    retire: () => {
      active = false;
    },
  };
}

it('sends the same scoped identity through both shared POST services and the owner-scoped lookup', async () => {
  const client = axios.create();
  const requests: { url: string; body: unknown; params: unknown }[] = [];
  client.defaults.adapter = async (config) => {
    requests.push({ url: config.url!, body: config.data ? JSON.parse(config.data) : undefined, params: config.params });
    return response(config, snapshot());
  };
  const request = { ...draft, submissionId, ownerAccountUuid: accountUuid };
  await getOrderCreateMessage(client, request);
  await createOrder(client, { ...request, digest: 'synthetic-digest', signature: 'synthetic-signature' });
  await getOrderSubmission(client, submissionId, accountUuid);
  expect(requests.map(({ url }) => url)).toEqual([
    endpoints.CREATE_MESSAGE,
    endpoints.CREATE,
    endpoints.SUBMISSION(submissionId),
  ]);
  for (const sent of requests.slice(0, 2))
    expect(sent.body).toMatchObject({
      submission_id: submissionId,
      owner_account_uuid: accountUuid,
      wallet_uuid: walletUuid,
      quantity: 10,
      price_per_share: '12.50',
    });
  expect(requests[2]!.params).toEqual({ owner_account_uuid: accountUuid });
});

it('recovers a lost create response after restart without re-signing or replacing its identity', async () => {
  const f = await setup();
  const requests: string[] = [];
  f.client.defaults.adapter = async (config) => {
    requests.push(config.url!);
    if (config.url === endpoints.CREATE_MESSAGE) return response(config, snapshot());
    if (config.url === endpoints.CREATE) throw new Error('Lost response after acceptance');
    return response(config, snapshot(submissionId, 'created'));
  };
  await f.selection.start(draft);
  await f.selection.submitSignature('synthetic-signature');
  expect(f.selection.getSnapshot().phase).toBe('error');
  expect(await f.store.list(owner)).toEqual([f.record]);
  f.selection.close();
  const restarted = f.make();
  await restarted.recover();
  expect(restarted.getSnapshot()).toMatchObject({
    phase: 'created',
    recovered: true,
    snapshot: { order: { status: 'cancelled', quantity: 7 } },
  });
  expect(requests).toEqual([endpoints.CREATE_MESSAGE, endpoints.CREATE, endpoints.SUBMISSION(submissionId)]);
  expect(f.newUuid).toHaveBeenCalledTimes(1);
  expect(await f.store.list(owner)).toEqual([]);
  expect(f.settled).toHaveBeenCalledTimes(1);
});

it('loads original terms before renewing an expired challenge under the original ID', async () => {
  const f = await setup();
  const requests: { url: string; body?: Record<string, unknown> }[] = [];
  f.client.defaults.adapter = async (config) => {
    requests.push({ url: config.url!, body: config.data ? JSON.parse(config.data) : undefined });
    const data = snapshot();
    if (requests.length === 1) data.challenge!.expiresAt = '2000-01-01T00:00:00Z';
    if (config.method === 'get') data.challenge = null;
    return response(config, data);
  };
  await f.selection.start(draft);
  const signer = jest.fn(async () => 'synthetic-signature');
  await f.selection.sign(signer);
  expect(signer).not.toHaveBeenCalled();
  expect(requests.map(({ url }) => url)).toEqual([
    endpoints.CREATE_MESSAGE,
    endpoints.SUBMISSION(submissionId),
    endpoints.CREATE_MESSAGE,
  ]);
  expect(requests[2]!.body).toMatchObject({
    submission_id: submissionId,
    quantity: 10,
    min_quantity: 2,
    price_per_share: '12.50',
  });
  expect(f.selection.getSnapshot().phase).toBe('ready');
});

it('keeps a restarted or expired submission unresolved when lookup says absent or inaccessible', async () => {
  const f = await setup();
  const requests: string[] = [];
  f.client.defaults.adapter = async (config) => {
    requests.push(config.url!);
    throw new AxiosError('Not found', undefined, config, undefined, response(config, { detail: 'Not found.' }, 404));
  };
  await f.selection.recover();
  await f.selection.submitSignature('must-not-send');
  expect(requests).toEqual([endpoints.SUBMISSION(submissionId)]);
  expect(f.selection.getSnapshot()).toMatchObject({ phase: 'error', challenge: null, snapshot: null });
  expect(await f.store.list(owner)).toEqual([f.record]);
  expect(f.newUuid).toHaveBeenCalledTimes(1);
});

it.each(['close', 'account'])('preserves a pending create and suppresses its late result after %s', async (reason) => {
  const f = await setup();
  const sent = deferred<void>();
  const result = deferred<AxiosResponse>();
  f.client.defaults.adapter = async (config) => {
    if (config.url === endpoints.CREATE_MESSAGE) return response(config, snapshot());
    sent.resolve();
    return result.promise;
  };
  await f.selection.start(draft);
  const posting = f.selection.submitSignature('synthetic-signature');
  await sent.promise;
  if (reason === 'close') f.selection.close();
  else f.retire();
  result.resolve({ data: snapshot(submissionId, 'created'), status: 201 } as AxiosResponse);
  await posting;
  expect(f.settled).not.toHaveBeenCalled();
  expect(await f.store.list(owner)).toEqual([f.record]);
});

it('latches concurrent signing and signature presses before asynchronous work', async () => {
  const f = await setup();
  const signature = deferred<string>();
  const requests: string[] = [];
  f.client.defaults.adapter = async (config) => {
    requests.push(config.url!);
    return response(
      config,
      snapshot(submissionId, config.url === endpoints.CREATE ? 'created' : 'pending'),
      config.url === endpoints.CREATE ? 201 : 200,
    );
  };
  await f.selection.start(draft);
  const signer = jest.fn(() => signature.promise);
  const first = f.selection.sign(signer);
  const duplicate = f.selection.sign(signer);
  await f.selection.submitSignature('other');
  signature.resolve('synthetic-signature');
  await Promise.all([first, duplicate]);
  expect(signer).toHaveBeenCalledTimes(1);
  expect(requests.filter((url) => url === endpoints.CREATE)).toHaveLength(1);
});

it.each(['submission', 'account', 'wallet', 'challenge'])(
  'refuses a mismatched %s response before signing',
  async (field) => {
    const f = await setup();
    const data = snapshot();
    if (field === 'submission') data.submissionId = secondId;
    if (field === 'account') data.ownerAccountUuid = otherAccountUuid;
    if (field === 'wallet') data.walletUuid = otherAccountUuid;
    if (field === 'challenge') data.challenge!.message.submissionId = secondId;
    f.client.defaults.adapter = async (config) => response(config, data);
    await f.selection.start(draft);
    expect(f.selection.getSnapshot().phase).toBe('error');
    const signer = jest.fn(async () => 'wrong');
    await f.selection.sign(signer);
    expect(signer).not.toHaveBeenCalled();
    expect(await f.store.list(owner)).toEqual([f.record]);
  },
);

it.each([true, false])('records only an authoritative terminal refusal (terminal=%s)', async (terminal) => {
  const f = await setup();
  f.client.defaults.adapter = async (config) => {
    if (config.url === endpoints.CREATE_MESSAGE) return response(config, snapshot());
    throw new AxiosError(
      'Refused',
      undefined,
      config,
      undefined,
      response(config, terminal ? snapshot(submissionId, 'refused') : { code: 'challenge_expired' }, 400),
    );
  };
  await f.selection.start(draft);
  await f.selection.submitSignature('synthetic-signature');
  expect(f.selection.getSnapshot().phase).toBe(terminal ? 'refused' : 'error');
  expect(await f.store.list(owner)).toHaveLength(terminal ? 0 : 1);
  expect(f.settled).toHaveBeenCalledTimes(terminal ? 1 : 0);
});
