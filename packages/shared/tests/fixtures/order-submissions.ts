import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import type { CreateOrderRequest, OrderSubmissionSnapshot, Wallet } from '../../src/types';
import type { OrderSubmissionStorage } from '../../src/utils/order-submission-storage';

export const userUuid = '10000000-0000-4000-8000-000000000001';
export const accountUuid = '20000000-0000-4000-8000-000000000001';
export const otherAccountUuid = '20000000-0000-4000-8000-000000000002';
export const walletUuid = '30000000-0000-4000-8000-000000000001';
export const tokenUuid = '40000000-0000-4000-8000-000000000001';
export const submissionId = '50000000-0000-4000-8000-000000000001';
export const secondId = '50000000-0000-4000-8000-000000000002';
export const wallet = {
  uuid: walletUuid,
  userAccount: accountUuid,
  address: '0x1111111111111111111111111111111111111111',
  derivationPath: "m/44'/60'/0'/0/0",
  masterFingerprint: '12345678',
  signingPreference: 'software',
  chain: 'ethereum',
} as unknown as Wallet;
export const owner = { userUuid, ownerAccountUuid: accountUuid };
export const draft: CreateOrderRequest = {
  token: tokenUuid,
  orderType: 'buy',
  walletUuid,
  walletAddress: wallet.address,
  quantity: 10,
  minQuantity: 2,
  pricePerShare: '12.50',
};
export function snapshot(
  id = submissionId,
  status: OrderSubmissionSnapshot['status'] = 'pending',
): OrderSubmissionSnapshot {
  return {
    submissionId: id,
    ownerAccountUuid: accountUuid,
    walletUuid,
    status,
    intent: {
      token: tokenUuid,
      orderType: 'buy',
      walletAddress: wallet.address,
      quantity: 10,
      minQuantity: 2,
      pricePerShare: '12.50',
    },
    challenge:
      status === 'pending'
        ? {
            purpose: 'order_create',
            tokenUuid,
            walletAddress: wallet.address,
            digest: '0x' + 'ab'.repeat(32),
            domain: {
              name: 'Ledova',
              version: '1',
              chainId: 31337,
              verifyingContract: '0x2222222222222222222222222222222222222222',
            },
            types: {},
            message: { submissionId: id, ownerAccountUuid: accountUuid, walletUuid, quantity: 10 },
            expiresAt: new Date(Date.now() + 60_000).toISOString(),
          }
        : null,
    order:
      status === 'created'
        ? {
            uuid: '60000000-0000-4000-8000-000000000001',
            token: tokenUuid,
            tokenSymbol: 'SYN',
            tokenName: 'Synthetic',
            orderType: 'buy',
            walletAddress: wallet.address,
            quantity: 7,
            pricePerShare: '14.00',
            status: 'cancelled',
            totalValue: '98.00',
            createdAt: '2026-01-01T00:00:00Z',
          }
        : null,
    refusal:
      status === 'refused' ? { code: 'insufficient_balance', detail: 'The wallet balance is insufficient.' } : null,
    match: null,
  };
}
export function response(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return { config, data, status, statusText: String(status), headers: {} };
}
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
export function memoryStorage() {
  const values = new Map<string, string>();
  const storage: OrderSubmissionStorage = {
    getAllKeys: () => [...values.keys()],
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, value);
    },
    removeItem: (key) => {
      values.delete(key);
    },
  };
  return { values, storage };
}
