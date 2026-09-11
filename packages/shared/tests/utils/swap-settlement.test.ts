import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import type { SavedSwapSettlement } from '../../src/utils/swap-settlement-storage';
import type { SwapSettlementResponse } from '../../src/types';
import { SwapSettlement } from '../../src/utils/swap-settlement';
import { createSwapSettlementStore } from '../../src/utils/swap-settlement-storage';
import { swapSettlementIdentity } from '../../src/utils/swap-settlement-validation';
import { deferred, memoryStorage, response as reply } from '../fixtures/order-submissions';
import {
  approvalHash,
  approvalRaw,
  settlementApproval,
  settlementCrypto,
  settlementFixture,
  settlementNow,
  settlementOwner,
  settlementResponse,
} from '../fixtures/swap-settlements';

function setup(response = settlementResponse()) {
  const { storage, values } = memoryStorage();
  const store = createSwapSettlementStore(storage);
  const api = axios.create();
  const crypto = settlementCrypto(response);
  const requests: InternalAxiosRequestConfig[] = [];
  let current = true;
  let handler = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => reply(config, response);
  api.interceptors.request.use((config) => {
    config.ledovaSubmissionGuard?.();
    return config;
  });
  api.defaults.adapter = async (config) => {
    requests.push(config);
    const result = await handler(config);
    return { ...result, data: JSON.stringify(result.data) };
  };
  const changed = jest.fn();
  const updated = jest.fn();
  const dependencies = {
    apiClient: api,
    crypto,
    store,
    isCurrent: () => current,
    onRecordsChanged: changed,
    onUpdated: updated,
  };
  const controller = new SwapSettlement(
    settlementOwner,
    {
      ...swapSettlementIdentity(response),
      walletAddress: response.swapOrder.settlementContext[response.userRole].address,
    },
    dependencies,
  );
  return {
    response,
    controller,
    api,
    store,
    storage,
    values,
    crypto,
    requests,
    changed,
    updated,
    dependencies,
    handle: (next: typeof handler) => {
      handler = next;
    },
    retire: () => {
      current = false;
    },
  };
}

function failed(config: InternalAxiosRequestConfig, status: number, data: unknown): never {
  throw new AxiosError('Synthetic failed response', String(status), config, undefined, reply(config, data, status));
}

function signedResponse(initial: SwapSettlementResponse, signer: 'seller' | 'buyer') {
  const value = JSON.parse(JSON.stringify(initial)) as SwapSettlementResponse;
  value.swapOrder[signer === 'seller' ? 'sellerHasSigned' : 'buyerHasSigned'] = true;
  value.swapOrder.status = signer === 'seller' ? 'seller_signed' : 'buyer_signed';
  value.hasSigned = value.userRole === signer;
  value.canSign = !value.hasSigned;
  return value;
}

function signatureRecord(
  response = settlementResponse(),
  signerAddress = settlementFixture.addresses[0]!,
): SavedSwapSettlement {
  return {
    version: 1,
    ...settlementOwner,
    ...swapSettlementIdentity(response),
    kind: 'signature',
    signerAddress: signerAddress.toLowerCase(),
  };
}

function approvalResult(response = settlementResponse()) {
  return {
    ...swapSettlementIdentity(response),
    userRole: response.userRole,
    txHash: approvalHash,
    blockNumber: 7,
    gasUsed: 42000,
  };
}

beforeEach(() => {
  jest.spyOn(Date, 'now').mockReturnValue(settlementNow);
});
afterEach(() => {
  jest.restoreAllMocks();
});

test('exact API context preserves large uint strings and frozen captured review across local signing', async () => {
  const f = setup();
  await f.controller.load();
  expect(f.controller.getSnapshot().response!.typedData.message.shareAmount).toBe('9007199254740993');
  expect(f.response.swapOrder.shareAmount.toString()).not.toBe('9007199254740993');
  let current = f.response;
  f.handle(async (config) => {
    if (config.method === 'post') {
      expect([...f.values.values()].map((value) => JSON.parse(value))).toEqual([signatureRecord()]);
      const body = JSON.parse(config.data);
      expect(body).toMatchObject({
        swap_uuid: current.swapUuid,
        owner_account_uuid: current.ownerAccountUuid,
        wallet_uuid: current.walletUuid,
        settlement_digest: current.settlementDigest,
        signature: settlementFixture.signatures[0],
      });
      current = signedResponse(current, 'seller');
      return reply(config, current.swapOrder);
    }
    return reply(config, current);
  });
  await f.controller.sign(async (typed, active) => {
    expect(active()).toBe(true);
    expect(typed).toEqual(settlementFixture.get_body.typedData);
    expect(Object.isFrozen(typed.message)).toBe(true);
    return { signature: settlementFixture.signatures[0]!, signerAddress: settlementFixture.addresses[0]! };
  });
  expect(f.updated).toHaveBeenCalledTimes(1);
  expect(f.controller.getSnapshot().response!.hasSigned).toBe(true);
  expect(f.values.size).toBe(0);
});

test('lost signature response survives restart and exact signer recovery without another POST', async () => {
  const f = setup();
  await f.controller.load();
  f.handle(async (config) => {
    if (config.method === 'post') throw new Error('Synthetic lost ACK');
    return reply(config, signedResponse(f.response, 'seller'));
  });
  await f.controller.submitSignature(settlementFixture.signatures[0]!, settlementFixture.addresses[0]!);
  expect(f.values.size).toBe(1);
  f.controller.close();
  const reminder = (await f.store.list(settlementOwner))[0]!;
  const reopened = new SwapSettlement(settlementOwner, reminder, f.dependencies);
  await reopened.recover();
  expect(reopened.getSnapshot().response!.hasSigned).toBe(true);
  expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(1);
  expect(f.values.size).toBe(0);
});

test('a stored caller signature does not erase an unobserved relayed counterparty reminder', async () => {
  const f = setup(signedResponse(settlementResponse(), 'seller'));
  await f.store.save(signatureRecord(f.response, settlementFixture.addresses[1]!));
  await f.controller.load();
  expect(f.values.size).toBe(1);
  f.handle(async (config) => {
    const updated = signedResponse(f.response, 'buyer');
    updated.hasSigned = true;
    updated.canSign = false;
    return reply(config, config.method === 'post' ? updated.swapOrder : updated);
  });
  await f.controller.submitSignature(settlementFixture.signatures[1]!, settlementFixture.addresses[1]!);
  expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(1);
  expect(f.values.size).toBe(0);
});

test.each([404, 409, 503])(
  'plain %s recovery retains all reminders and never changes the selected swap',
  async (status) => {
    const f = setup();
    await f.store.save(signatureRecord());
    f.handle(async (config) => failed(config, status, { detail: 'Synthetic refused context' }));
    await f.controller.recover();
    expect(f.controller.getSnapshot().phase).toBe('error');
    expect(f.values.size).toBe(1);
    expect(f.requests).toHaveLength(1);
    expect(f.requests[0]!.params.swap_uuid).toBe(f.response.swapUuid);
  },
);

test('duplicate presses share a single admitted signer and signature POST', async () => {
  const f = setup();
  await f.controller.load();
  const held = deferred<{ signature: string; signerAddress: string } | null>();
  const signer = jest.fn(() => held.promise);
  f.handle(async (config) =>
    reply(
      config,
      config.method === 'post' ? signedResponse(f.response, 'seller').swapOrder : signedResponse(f.response, 'seller'),
    ),
  );
  const first = f.controller.sign(signer);
  await f.controller.sign(signer);
  await f.controller.submitSignature(settlementFixture.signatures[0]!, settlementFixture.addresses[0]!);
  held.resolve({ signature: settlementFixture.signatures[0]!, signerAddress: settlementFixture.addresses[0]! });
  await first;
  expect(signer).toHaveBeenCalledTimes(1);
  expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(1);
});

test('closing during a seed/signing read invalidates its continuation and prevents persistence or POST', async () => {
  const f = setup();
  await f.controller.load();
  const held = deferred<{ signature: string; signerAddress: string } | null>();
  let signingCurrent = () => false;
  const pending = f.controller.sign(async (_typed, current) => {
    signingCurrent = current;
    return held.promise;
  });
  f.controller.close();
  expect(signingCurrent()).toBe(false);
  held.resolve({ signature: settlementFixture.signatures[0]!, signerAddress: settlementFixture.addresses[0]! });
  await pending;
  expect(f.values.size).toBe(0);
  expect(f.requests).toHaveLength(1);
  expect(f.updated).not.toHaveBeenCalled();
});

test('session retirement during local digest verification never publishes the old context', async () => {
  const f = setup();
  const held = deferred<string>();
  f.crypto.digestTypedData = () => held.promise;
  const pending = f.controller.load();
  await Promise.resolve();
  await Promise.resolve();
  f.retire();
  held.resolve(f.response.settlementDigest);
  await pending;
  expect(f.controller.getSnapshot().response).toBeNull();
  expect(f.updated).not.toHaveBeenCalled();
});

test.each(['signature', 'approval'] as const)(
  'account changes during %s persistence preserve the reminder and prevent sending',
  async (kind) => {
    const f = setup();
    await f.controller.load();
    f.handle(async (config) => reply(config, settlementApproval()));
    if (kind === 'approval') await f.controller.prepareApproval();
    const entered = deferred<void>();
    const finish = deferred<void>();
    const original = f.storage.setItem;
    f.storage.setItem = async (key, value) => {
      original(key, value);
      entered.resolve();
      await finish.promise;
    };
    const pending =
      kind === 'approval'
        ? f.controller.broadcastApproval(approvalRaw)
        : f.controller.submitSignature(settlementFixture.signatures[0]!, settlementFixture.addresses[0]!);
    await entered.promise;
    f.retire();
    finish.resolve();
    await pending;
    expect(f.values.size).toBe(1);
    expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(0);
  },
);

test.each(['signature', 'approval'] as const)(
  'ambiguous %s storage failure prevents the first POST and retains its written identifiers',
  async (kind) => {
    const f = setup();
    await f.controller.load();
    f.handle(async (config) => reply(config, settlementApproval()));
    if (kind === 'approval') await f.controller.prepareApproval();
    const original = f.storage.setItem;
    f.storage.setItem = (key, value) => {
      original(key, value);
      throw new Error('Synthetic failed persistence acknowledgement');
    };
    if (kind === 'approval') await f.controller.broadcastApproval(approvalRaw);
    else await f.controller.submitSignature(settlementFixture.signatures[0]!, settlementFixture.addresses[0]!);
    expect(f.controller.getSnapshot().phase).toBe('error');
    expect(f.values.size).toBe(1);
    expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(0);
  },
);

test('refresh finishing after close cannot replay a stale POST; an unrelated request retains its retry', async () => {
  const f = setup();
  await f.controller.load();
  const held = deferred<void>();
  const entered = deferred<void>();
  const retried = new Set<string>();
  f.api.interceptors.response.use(undefined, async (error: AxiosError) => {
    if (error.response?.status !== 403) throw error;
    entered.resolve();
    await held.promise;
    return f.api.request(error.config!);
  });
  f.handle(async (config) => {
    const url = config.url!;
    if (!retried.has(url)) {
      retried.add(url);
      failed(config, 403, { detail: 'Synthetic refresh' });
    }
    return reply(config, { ok: true });
  });
  const pending = f.controller.submitSignature(settlementFixture.signatures[0]!, settlementFixture.addresses[0]!);
  await entered.promise;
  f.controller.close();
  held.resolve();
  await pending;
  expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(1);
  expect(f.values.size).toBe(1);
  expect((await f.api.get('/unrelated')).data).toEqual({ ok: true });
  expect(f.requests.filter((request) => request.url === '/unrelated')).toHaveLength(2);
});

test('valid scoped503 approval remains visibly unresolved after restart and later sufficient allowance', async () => {
  const f = setup();
  await f.controller.load();
  let sufficient = false;
  f.handle(async (config) => {
    if (config.method === 'post')
      failed(config, 503, {
        ...swapSettlementIdentity(f.response),
        userRole: 'seller',
        txHash: approvalHash,
        code: 'swap_approval_unconfirmed',
        detail: 'Synthetic unconfirmed',
      });
    if (config.url?.endsWith('approval-data/')) return reply(config, settlementApproval());
    if (config.url?.endsWith('approval-status/'))
      return reply(config, {
        ...settlementApproval(),
        requiredAmount: f.response.typedData.message.shareAmount,
        currentAllowance: sufficient ? f.response.typedData.message.shareAmount : '0',
        needsApproval: !sufficient,
      });
    return reply(config, f.response);
  });
  await f.controller.prepareApproval();
  await f.controller.broadcastApproval(approvalRaw);
  expect(f.controller.getSnapshot().approvalResult).toMatchObject({
    code: 'swap_approval_unconfirmed',
    txHash: approvalHash,
  });
  expect(f.values.size).toBe(1);
  f.controller.close();
  const reminder = (await f.store.list(settlementOwner))[0]!;
  const reopened = new SwapSettlement(settlementOwner, reminder, f.dependencies);
  await reopened.load();
  expect(reopened.getSnapshot().unconfirmedApprovalHashes).toEqual([approvalHash]);
  await reopened.prepareApproval();
  expect(reopened.getSnapshot().error).toMatch(/earlier approval remains unconfirmed/);
  await reopened.broadcastApproval(approvalRaw);
  sufficient = true;
  await reopened.refreshApprovalStatus();
  expect(reopened.getSnapshot().approvalStatus!.needsApproval).toBe(false);
  expect(reopened.getSnapshot().unconfirmedApprovalHashes).toEqual([approvalHash]);
  expect(reopened.getSnapshot().approvalResult).toBeNull();
  expect(f.values.size).toBe(1);
  expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(1);
});

test('approval confirmation remains attributed to its original hash after the deadline passes during receipt wait', async () => {
  const f = setup();
  await f.controller.load();
  f.handle(async (config) => {
    if (config.method === 'post') {
      jest.mocked(Date.now).mockReturnValue(settlementNow + 1000000);
      return reply(config, approvalResult());
    }
    return reply(config, settlementApproval());
  });
  await f.controller.prepareApproval();
  await f.controller.signApproval(async (_tx, current) => {
    expect(current()).toBe(true);
    return approvalRaw;
  });
  expect(f.controller.getSnapshot().approvalResult).toEqual(approvalResult());
  expect(f.values.size).toBe(0);
  expect(f.updated).toHaveBeenCalledTimes(1);
});

test.each(['swapUuid', 'walletUuid', 'settlementDigest', 'txHash', 'code'] as const)(
  'mismatched approval uncertainty %s cannot confirm or clear the saved hash',
  async (field) => {
    const f = setup();
    await f.controller.load();
    f.handle(async (config) => {
      if (config.method === 'post')
        failed(config, 503, {
          ...swapSettlementIdentity(f.response),
          userRole: 'seller',
          txHash: approvalHash,
          code: 'swap_approval_unconfirmed',
          detail: 'Synthetic uncertainty',
          [field]: field === 'txHash' ? '0x' + 'ff'.repeat(32) : 'wrong',
        });
      return reply(config, settlementApproval());
    });
    await f.controller.prepareApproval();
    await f.controller.broadcastApproval(approvalRaw);
    expect(f.controller.getSnapshot().phase).toBe('error');
    expect(f.controller.getSnapshot().approvalResult).toBeNull();
    expect(f.values.size).toBe(1);
  },
);

test('approval decoder finishing after closure cannot persist or broadcast its old transaction', async () => {
  const f = setup();
  await f.controller.load();
  f.handle(async (config) => reply(config, settlementApproval()));
  await f.controller.prepareApproval();
  const held = deferred<{ txHash: string; transaction: ReturnType<typeof settlementApproval>['transaction'] }>();
  f.crypto.inspectSignedApproval = () => held.promise;
  const pending = f.controller.broadcastApproval(approvalRaw);
  f.controller.close();
  held.resolve({ txHash: approvalHash, transaction: settlementApproval().transaction });
  await pending;
  expect(f.values.size).toBe(0);
  expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(0);
});

test('expiry while signing or an expired recovered context refuses new work without rewriting its deadline', async () => {
  const f = setup();
  await f.controller.load();
  const originalDeadline = f.controller.getSnapshot().response!.typedData.message.deadline;
  await f.controller.sign(async (_typed, current) => {
    jest.mocked(Date.now).mockReturnValue(settlementNow + 1000000);
    expect(current()).toBe(false);
    return { signature: settlementFixture.signatures[0]!, signerAddress: settlementFixture.addresses[0]! };
  });
  expect(f.controller.getSnapshot().error).toMatch(/Refresh the original/);
  expect(f.values.size).toBe(0);
  expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(0);
  expect(f.controller.getSnapshot().response!.typedData.message.deadline).toBe(originalDeadline);
});

test('closure after an accepted POST retains its reminder and suppresses the old result callback', async () => {
  const f = setup();
  await f.controller.load();
  const entered = deferred<InternalAxiosRequestConfig>();
  const held = deferred<AxiosResponse>();
  f.handle(async (config) => {
    entered.resolve(config);
    return held.promise;
  });
  const pending = f.controller.submitSignature(settlementFixture.signatures[0]!, settlementFixture.addresses[0]!);
  const request = await entered.promise;
  f.controller.close();
  held.resolve(reply(request, signedResponse(f.response, 'seller').swapOrder));
  await pending;
  expect(f.values.size).toBe(1);
  expect(f.updated).not.toHaveBeenCalled();
});

test('uncertain signature delivery requires exact recovery before another signer even after an allowance check', async () => {
  const f = setup();
  await f.controller.load();
  f.handle(async (config) => {
    if (config.method === 'post') throw new Error('Synthetic lost ACK');
    return reply(config, {
      ...settlementApproval(),
      requiredAmount: f.response.typedData.message.shareAmount,
      currentAllowance: f.response.typedData.message.shareAmount,
      needsApproval: false,
    });
  });
  await f.controller.submitSignature(settlementFixture.signatures[0]!, settlementFixture.addresses[0]!);
  await f.controller.refreshApprovalStatus();
  const signer = jest.fn(async () => ({
    signature: settlementFixture.signatures[0]!,
    signerAddress: settlementFixture.addresses[0]!,
  }));
  await f.controller.sign(signer);
  expect(signer).not.toHaveBeenCalled();
  expect(f.controller.getSnapshot().error).toMatch(/saved settlement status/);
  expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(1);
  expect(f.values.size).toBe(1);
});

test.each(['digest', 'signer', 'approval-decoder'] as const)(
  'unexpected %s errors cannot display raw signing material',
  async (operation) => {
    const f = setup();
    const unsafe = 'Synthetic private signing material must stay private';
    if (operation === 'digest')
      f.crypto.digestTypedData = () => {
        throw new Error(unsafe);
      };
    await f.controller.load();
    if (operation === 'signer')
      await f.controller.sign(async () => {
        throw new Error(unsafe);
      });
    if (operation === 'approval-decoder') {
      f.handle(async (config) => reply(config, settlementApproval()));
      await f.controller.prepareApproval();
      f.crypto.inspectSignedApproval = () => {
        throw new Error(unsafe);
      };
      await f.controller.broadcastApproval(approvalRaw);
    }
    expect(f.controller.getSnapshot().phase).toBe('error');
    expect(f.controller.getSnapshot().error).not.toContain(unsafe);
    expect(f.values.size).toBe(0);
    expect(f.requests.filter((request) => request.method === 'post')).toHaveLength(0);
  },
);

test('an observed wallet/session retirement cannot revive the old controller when the live guard later becomes true', async () => {
  const f = setup();
  await f.controller.load();
  f.retire();
  expect(f.controller.isCurrent()).toBe(false);
  f.dependencies.isCurrent = () => true;
  expect(f.controller.isCurrent()).toBe(false);
  const signer = jest.fn(async () => ({
    signature: settlementFixture.signatures[0]!,
    signerAddress: settlementFixture.addresses[0]!,
  }));
  await f.controller.sign(signer);
  expect(signer).not.toHaveBeenCalled();
});
