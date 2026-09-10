export interface OrderSubmissionOwner {
  userUuid: string;
  ownerAccountUuid: string;
}

export interface SavedOrderSubmission extends OrderSubmissionOwner {
  version: 1;
  walletUuid: string;
  submissionId: string;
}

export interface OrderSubmissionStorage {
  getAllKeys: () => readonly string[] | Promise<readonly string[]>;
  getItem: (key: string) => string | null | Promise<string | null>;
  setItem: (key: string, value: string) => void | Promise<void>;
  removeItem: (key: string) => void | Promise<void>;
}

const PREFIX = 'ledova.order-submissions.v1.';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function scopePrefix(owner: OrderSubmissionOwner): string {
  if (!UUID.test(owner.userUuid) || !UUID.test(owner.ownerAccountUuid))
    throw new Error('Order account is unavailable.');
  return `${PREFIX}${owner.userUuid}.${owner.ownerAccountUuid}.`;
}

function storageKey(record: SavedOrderSubmission): string {
  if (!UUID.test(record.walletUuid) || !UUID.test(record.submissionId))
    throw new Error('Order identity is unavailable.');
  return `${scopePrefix(record)}${record.walletUuid}.${record.submissionId}`;
}

function decodeRecord(value: string, key: string): SavedOrderSubmission {
  const record: SavedOrderSubmission = JSON.parse(value);
  if (
    !record ||
    record.version !== 1 ||
    Object.keys(record).sort().join(',') !== 'ownerAccountUuid,submissionId,userUuid,version,walletUuid' ||
    storageKey(record) !== key
  )
    throw new Error('Saved order information could not be read.');
  return record;
}

export function createOrderSubmissionStore(storage: OrderSubmissionStorage, newUuid: () => string) {
  const list = async (owner: OrderSubmissionOwner): Promise<SavedOrderSubmission[]> => {
    const prefix = scopePrefix(owner);
    const keys = (await storage.getAllKeys()).filter((key) => key.startsWith(prefix)).sort();
    const records = await Promise.all(
      keys.map(async (key) => {
        const value = await storage.getItem(key);
        return value === null ? null : decodeRecord(value, key);
      }),
    );
    return records.filter((record): record is SavedOrderSubmission => record !== null);
  };

  const reserve = (owner: OrderSubmissionOwner, walletUuid: string): SavedOrderSubmission => {
    const record: SavedOrderSubmission = {
      version: 1,
      userUuid: owner.userUuid,
      ownerAccountUuid: owner.ownerAccountUuid,
      walletUuid,
      submissionId: newUuid(),
    };
    storageKey(record);
    return Object.freeze(record);
  };

  const persist = async (record: SavedOrderSubmission, retry = false): Promise<SavedOrderSubmission> => {
    const key = storageKey(record);
    const value = JSON.stringify(record);
    await list(record);
    const existing = await storage.getItem(key);
    if (existing !== null && (!retry || existing !== value)) throw new Error('This saved order already exists.');
    await storage.setItem(key, value);
    if ((await storage.getItem(key)) !== value) throw new Error('The order could not be saved on this device.');
    return record;
  };

  return {
    list,
    reserve,
    persist,
    create: (owner: OrderSubmissionOwner, walletUuid: string): Promise<SavedOrderSubmission> =>
      persist(reserve(owner, walletUuid)),
    async remove(record: SavedOrderSubmission): Promise<void> {
      const key = storageKey(record);
      await storage.removeItem(key);
      if ((await storage.getItem(key)) !== null) throw new Error('The saved order reminder could not be cleared.');
    },
  };
}

export type OrderSubmissionStore = ReturnType<typeof createOrderSubmissionStore>;
