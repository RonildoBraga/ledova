import { createSwapSettlementStore, type SavedSwapSettlement } from '../../src/utils/swap-settlement-storage';
import { swapSettlementIdentity } from '../../src/utils/swap-settlement-validation';
import { memoryStorage } from '../fixtures/order-submissions';
import { approvalHash, settlementFixture, settlementOwner, settlementResponse } from '../fixtures/swap-settlements';

const signature: SavedSwapSettlement = {
  version: 1,
  ...settlementOwner,
  ...swapSettlementIdentity(settlementResponse()),
  kind: 'signature',
  signerAddress: settlementFixture.addresses[0]!.toLowerCase(),
};

test('multiple exact signature/approval/swap reminders survive adapter recreation and stay owner scoped', async () => {
  const { storage, values } = memoryStorage();
  const store = createSwapSettlementStore(storage);
  const approval: SavedSwapSettlement = {
    version: 1,
    ...settlementOwner,
    ...swapSettlementIdentity(settlementResponse()),
    kind: 'approval',
    txHash: approvalHash,
  };
  const otherSwap = { ...signature, swapUuid: '30000000-0000-4000-8000-000000000099' };
  const otherOwner = { ...signature, userUuid: '10000000-0000-4000-8000-000000000099' };
  for (const record of [signature, approval, otherSwap, otherOwner]) await store.save(record);
  const restored = createSwapSettlementStore(storage);
  expect(await restored.list(settlementOwner)).toHaveLength(3);
  expect(await restored.list(otherOwner)).toEqual([otherOwner]);
  await restored.save(signature);
  await restored.remove(signature);
  expect(await restored.list(settlementOwner)).toHaveLength(2);
  expect(values.size).toBe(3);
});

test.each(['signature', 'typedData', 'rawTransaction', 'seed', 'extra'])(
  'persisted records reject unexpected %s data before writing',
  async (field) => {
    const { storage, values } = memoryStorage();
    const store = createSwapSettlementStore(storage);
    await expect(store.save({ ...signature, [field]: 'synthetic forbidden content' })).rejects.toThrow();
    expect(values.size).toBe(0);
    await expect(store.save(signature)).resolves.toBeUndefined();
    expect(values.size).toBe(1);
  },
);

test('malformed matching-scope records stop writes while unrelated owner records are not parsed', async () => {
  const { storage, values } = memoryStorage();
  const store = createSwapSettlementStore(storage);
  await store.save(signature);
  const key = [...values.keys()][0]!;
  values.set(key, '{');
  await expect(store.list(settlementOwner)).rejects.toThrow();
  await expect(store.save(signature)).rejects.toThrow();
  expect(await store.list({ ...settlementOwner, userUuid: '10000000-0000-4000-8000-000000000099' })).toEqual([]);
});

test('write/readback mismatch and failed deletion are never reported successful', async () => {
  const { storage, values } = memoryStorage();
  const store = createSwapSettlementStore(storage);
  storage.setItem = () => {};
  await expect(store.save(signature)).rejects.toThrow(/could not be saved/);
  storage.setItem = (key, value) => {
    values.set(key, value);
  };
  await store.save(signature);
  storage.removeItem = () => {};
  await expect(store.remove(signature)).rejects.toThrow(/could not be cleared/);
  expect(values.size).toBe(1);
});
