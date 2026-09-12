import { SwapSettlementError } from './swap-settlement-error';
import type { SwapSettlementIdentity } from '../types';
import type { OrderSubmissionOwner, OrderSubmissionStorage } from './order-submission-storage';

export type SavedSwapSettlement = OrderSubmissionOwner &
  SwapSettlementIdentity & { version: 1 } & (
    { kind: 'signature'; signerAddress: string } | { kind: 'approval'; txHash: string }
  );

const PREFIX = 'ledova.swap-settlements.v1.';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const HASH = /^0x[0-9a-f]{64}$/i;

function scopePrefix(owner: OrderSubmissionOwner): string {
  if (!UUID.test(owner.userUuid) || !UUID.test(owner.ownerAccountUuid))
    throw new SwapSettlementError('The settlement account is unavailable.');
  return `${PREFIX}${owner.userUuid}.${owner.ownerAccountUuid}.`;
}

function storageKey(record: SavedSwapSettlement): string {
  const keys = 'kind,orderUuid,ownerAccountUuid,settlementDigest,swapUuid,userUuid,version,walletUuid';
  if (
    !record ||
    record.version !== 1 ||
    ![record.orderUuid, record.swapUuid, record.walletUuid].every((id) => typeof id === 'string' && UUID.test(id)) ||
    !HASH.test(record.settlementDigest) ||
    !['signature', 'approval'].includes(record.kind) ||
    Object.keys(record).sort().join(',') !==
      [...keys.split(','), record.kind === 'signature' ? 'signerAddress' : 'txHash'].sort().join(',') ||
    (record.kind === 'signature' ? !/^0x[0-9a-f]{40}$/i.test(record.signerAddress) : !HASH.test(record.txHash))
  )
    throw new SwapSettlementError('Saved settlement information could not be read.');
  const operation = record.kind === 'signature' ? record.signerAddress.toLowerCase() : record.txHash.toLowerCase();
  return `${scopePrefix(record)}${record.orderUuid}.${record.swapUuid}.${record.walletUuid}.${record.settlementDigest.toLowerCase()}.${record.kind}.${operation}`;
}

export function createSwapSettlementStore(storage: OrderSubmissionStorage) {
  const list = async (owner: OrderSubmissionOwner): Promise<SavedSwapSettlement[]> => {
    const prefix = scopePrefix(owner);
    const keys = (await storage.getAllKeys()).filter((key) => key.startsWith(prefix)).sort();
    const records = await Promise.all(
      keys.map(async (key) => {
        const value = await storage.getItem(key);
        if (value === null) return null;
        const record: SavedSwapSettlement = JSON.parse(value);
        if (storageKey(record) !== key)
          throw new SwapSettlementError('Saved settlement information did not match its account.');
        return record;
      }),
    );
    return records.filter((record): record is SavedSwapSettlement => record !== null);
  };
  return {
    list,
    async save(record: SavedSwapSettlement): Promise<void> {
      const key = storageKey(record);
      const value = JSON.stringify(record);
      await list(record);
      const existing = await storage.getItem(key);
      if (existing !== null && existing !== value)
        throw new SwapSettlementError('This settlement reminder already differs.');
      await storage.setItem(key, value);
      if ((await storage.getItem(key)) !== value)
        throw new SwapSettlementError('The settlement could not be saved on this device.');
    },
    async remove(record: SavedSwapSettlement): Promise<void> {
      const key = storageKey(record);
      const existing = await storage.getItem(key);
      if (existing !== null && existing !== JSON.stringify(record))
        throw new SwapSettlementError('This settlement reminder changed before it could be cleared.');
      await storage.removeItem(key);
      if ((await storage.getItem(key)) !== null)
        throw new SwapSettlementError('The settlement reminder could not be cleared.');
    },
  };
}

export type SwapSettlementStore = ReturnType<typeof createSwapSettlementStore>;
