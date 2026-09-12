import type { OrderActionPurpose } from '../types';
import type { OrderSubmissionOwner, OrderSubmissionStorage } from './order-submission-storage';

export interface SavedOrderAction extends OrderSubmissionOwner {
  version: 1;
  actionId: string;
  orderUuid: string;
  purpose: OrderActionPurpose;
}

const PREFIX = 'ledova.order-actions.v1.';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function scopePrefix(owner: OrderSubmissionOwner): string {
  if (!UUID.test(owner.userUuid) || !UUID.test(owner.ownerAccountUuid))
    throw new Error('The order account is unavailable.');
  return `${PREFIX}${owner.userUuid}.${owner.ownerAccountUuid}.`;
}

function storageKey(record: SavedOrderAction): string {
  if (!UUID.test(record.orderUuid) || !UUID.test(record.actionId) || !['cancel', 'modify'].includes(record.purpose))
    throw new Error('The order action identity is unavailable.');
  return `${scopePrefix(record)}${record.orderUuid}.${record.purpose}.${record.actionId}`;
}

function decode(value: string, key: string): SavedOrderAction {
  const record: SavedOrderAction = JSON.parse(value);
  if (
    !record ||
    record.version !== 1 ||
    Object.keys(record).sort().join(',') !== 'actionId,orderUuid,ownerAccountUuid,purpose,userUuid,version' ||
    storageKey(record) !== key
  )
    throw new Error('The saved cancellation or change could not be read.');
  return record;
}

export function createOrderActionStore(storage: OrderSubmissionStorage, newUuid: () => string) {
  const attemptedWrites = new WeakSet<SavedOrderAction>();
  const list = async (owner: OrderSubmissionOwner): Promise<SavedOrderAction[]> => {
    const prefix = scopePrefix(owner);
    const keys = (await storage.getAllKeys()).filter((key) => key.startsWith(prefix)).sort();
    const records = await Promise.all(
      keys.map(async (key) => {
        const value = await storage.getItem(key);
        return value === null ? null : decode(value, key);
      }),
    );
    return records.filter((record): record is SavedOrderAction => record !== null);
  };
  return {
    list,
    reserve(owner: OrderSubmissionOwner, orderUuid: string, purpose: OrderActionPurpose): SavedOrderAction {
      const record: SavedOrderAction = {
        version: 1,
        userUuid: owner.userUuid,
        ownerAccountUuid: owner.ownerAccountUuid,
        orderUuid,
        purpose,
        actionId: newUuid(),
      };
      storageKey(record);
      return Object.freeze(record);
    },
    async persist(record: SavedOrderAction, retry = false): Promise<void> {
      const key = storageKey(record);
      const value = JSON.stringify(record);
      await list(record);
      const existing = await storage.getItem(key);
      if (existing !== null && (!retry || !attemptedWrites.has(record) || existing !== value))
        throw new Error('This saved action already exists.');
      attemptedWrites.add(record);
      await storage.setItem(key, value);
      if ((await storage.getItem(key)) !== value) throw new Error('This action could not be saved on this device.');
    },
    async remove(record: SavedOrderAction): Promise<void> {
      const key = storageKey(record);
      await storage.removeItem(key);
      if ((await storage.getItem(key)) !== null) throw new Error('The saved action reminder could not be cleared.');
    },
  };
}

export type OrderActionStore = ReturnType<typeof createOrderActionStore>;
