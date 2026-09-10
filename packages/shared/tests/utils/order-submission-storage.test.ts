import { createOrderSubmissionStore } from '../../src/utils/order-submission-storage';
import {
  accountUuid,
  deferred,
  memoryStorage,
  otherAccountUuid,
  owner,
  secondId,
  submissionId,
  userUuid,
  walletUuid,
} from '../fixtures/order-submissions';

it('persists multiple independent identities using only scoped IDs and protocol version', async () => {
  const { values, storage } = memoryStorage();
  const ids = [submissionId, secondId];
  const store = createOrderSubmissionStore(storage, () => ids.shift()!);
  const [first, second] = await Promise.all([store.create(owner, walletUuid), store.create(owner, walletUuid)]);
  expect(first.submissionId).not.toBe(second.submissionId);
  expect(values.size).toBe(2);
  for (const value of values.values()) {
    expect(Object.keys(JSON.parse(value)).sort()).toEqual([
      'ownerAccountUuid',
      'submissionId',
      'userUuid',
      'version',
      'walletUuid',
    ]);
    expect(JSON.parse(value)).toMatchObject({ userUuid, ownerAccountUuid: accountUuid, walletUuid, version: 1 });
  }
  const restarted = createOrderSubmissionStore(storage, () => {
    throw new Error('Recovery must not allocate');
  });
  expect(await restarted.list(owner)).toEqual([first, second]);
  expect(await restarted.list({ ...owner, ownerAccountUuid: otherAccountUuid })).toEqual([]);
  await restarted.remove(first);
  expect(await restarted.list(owner)).toEqual([second]);
});

it.each(['enumerate', 'read', 'write', 'verification'])('fails closed on %s storage failure', async (operation) => {
  const { values, storage } = memoryStorage();
  if (operation === 'enumerate')
    storage.getAllKeys = () => {
      throw new Error('Unavailable');
    };
  if (operation === 'read')
    storage.getItem = () => {
      throw new Error('Unavailable');
    };
  if (operation === 'write')
    storage.setItem = () => {
      throw new Error('Unavailable');
    };
  if (operation === 'verification') storage.setItem = () => {};
  const store = createOrderSubmissionStore(storage, () => submissionId);
  await expect(store.create(owner, walletUuid)).rejects.toThrow();
  expect(values.size).toBe(0);
});

it('does not overwrite an existing identity or discard unreadable same-account records', async () => {
  const { values, storage } = memoryStorage();
  const store = createOrderSubmissionStore(storage, () => submissionId);
  const record = await store.create(owner, walletUuid);
  await expect(store.create(owner, walletUuid)).rejects.toThrow('already exists');
  expect(await store.list(owner)).toEqual([record]);
  values.set([...values.keys()][0]!, '{invalid');
  const next = createOrderSubmissionStore(storage, () => secondId);
  await expect(next.create(owner, walletUuid)).rejects.toThrow();
  expect(values.size).toBe(1);
});

it('detects a resolved no-op deletion without affecting another record', async () => {
  const { storage } = memoryStorage();
  const store = createOrderSubmissionStore(storage, () => submissionId);
  const record = await store.create(owner, walletUuid);
  storage.removeItem = () => {};
  await expect(store.remove(record)).rejects.toThrow('could not be cleared');
  expect(await store.list(owner)).toEqual([record]);
});

it('does not admit an identity before its actual persistent write resolves', async () => {
  const { values, storage } = memoryStorage();
  const write = deferred<void>();
  const entered = deferred<void>();
  storage.setItem = async (key, value) => {
    entered.resolve();
    await write.promise;
    values.set(key, value);
  };
  const store = createOrderSubmissionStore(storage, () => submissionId);
  let admitted = false;
  const saving = store.create(owner, walletUuid).then(() => {
    admitted = true;
  });
  await entered.promise;
  expect(admitted).toBe(false);
  write.resolve();
  await saving;
  expect(admitted).toBe(true);
});
