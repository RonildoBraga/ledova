import type { OrderActionContext, OrderActionPurpose, OrderActionSnapshot, OrderActionValues } from '../../src/types';
import { accountUuid, tokenUuid, wallet, walletUuid } from './order-submissions';

export const orderUuid = '60000000-0000-4000-8000-000000000001';
export const otherOrderUuid = '60000000-0000-4000-8000-000000000002';
export const actionId = '70000000-0000-4000-8000-000000000001';
export const otherActionId = '70000000-0000-4000-8000-000000000002';
export const largeQuantity = '9007199254740993';
export const largeMinimum = '9007199254740992';

export function actionContext(quantity = '10', minimum = '2'): OrderActionContext {
  return {
    protocolVersion: 1,
    ownerAccountUuid: accountUuid,
    orderUuid,
    walletUuid,
    tokenUuid,
    walletAddress: wallet.address,
    domain: {
      name: 'Ledova Trading',
      version: '1',
      chainId: 31337,
      verifyingContract: '0x2222222222222222222222222222222222222222',
    },
    token: { name: 'Synthetic', symbol: 'SYN', contractAddress: '0x2222222222222222222222222222222222222222' },
    currentValues: {
      orderType: 'sell',
      status: 'open',
      modificationCount: 0,
      canCancel: true,
      canModify: true,
      quantity,
      minQuantity: minimum,
      pricePerShare: '12.50',
      filledQuantity: '0',
      remainingQuantity: quantity,
    },
  };
}

export function actionSnapshot(
  purpose: OrderActionPurpose = 'modify',
  status: OrderActionSnapshot['status'] = 'pending',
  context = actionContext(),
  replacements: OrderActionValues = {
    quantity: context.currentValues.quantity,
    minQuantity: context.currentValues.minQuantity,
    pricePerShare: '14.00',
  },
  id = actionId,
): OrderActionSnapshot {
  const expiry = Date.now() + 60_000;
  const fields = [
    { name: 'actionId', type: 'string' },
    { name: 'protocolVersion', type: 'uint256' },
    { name: 'ownerAccountUuid', type: 'string' },
    { name: 'walletUuid', type: 'string' },
    { name: 'tokenUuid', type: 'string' },
    { name: 'orderUuid', type: 'string' },
    ...(purpose === 'modify'
      ? [
          { name: 'newQuantity', type: 'uint256' },
          { name: 'newMinQuantity', type: 'uint256' },
          { name: 'newPricePerShare', type: 'string' },
        ]
      : []),
    { name: 'wallet', type: 'address' },
    { name: 'nonce', type: 'uint256' },
    { name: 'deadline', type: 'uint256' },
  ];
  return {
    protocolVersion: 1,
    actionId: id,
    ownerAccountUuid: context.ownerAccountUuid,
    orderUuid: context.orderUuid,
    walletUuid: context.walletUuid,
    tokenUuid: context.tokenUuid,
    walletAddress: context.walletAddress,
    purpose,
    status,
    intent: { domain: context.domain, modifications: purpose === 'modify' ? replacements : null },
    review: { token: context.token, currentValues: context.currentValues },
    order: {
      uuid: context.orderUuid,
      token: context.tokenUuid,
      tokenName: 'Current Synthetic',
      tokenSymbol: 'SYN',
      walletAddress: context.walletAddress,
      orderType: 'sell',
      status: status === 'applied' ? 'cancelled' : 'open',
      quantity: Number(context.currentValues.quantity),
      minQuantity: Number(context.currentValues.minQuantity),
      pricePerShare: status === 'applied' ? '15.00' : context.currentValues.pricePerShare,
      totalValue: '150.00',
      createdAt: '2026-01-01T00:00:00Z',
    },
    result:
      status !== 'applied'
        ? null
        : purpose === 'cancel'
          ? { kind: 'cancel', fromStatus: 'open', toStatus: 'cancelled' }
          : {
              kind: 'modify',
              modificationCount: 1,
              changes: [
                { field: 'price_per_share', old: context.currentValues.pricePerShare, new: replacements.pricePerShare },
              ],
            },
    refusal:
      status !== 'refused'
        ? null
        : purpose === 'cancel'
          ? { code: 'order_cancellation_failed', httpStatus: 400, detail: 'The order can no longer be cancelled.' }
          : { code: 'order_modification_conflict', httpStatus: 409, detail: 'The order has a pending swap.' },
    challenge:
      status !== 'pending'
        ? null
        : {
            purpose: purpose === 'cancel' ? 'order_cancel' : 'order_modify',
            domain: context.domain,
            types: { [purpose === 'cancel' ? 'OrderCancelV1' : 'OrderModifyV1']: fields },
            digest: '0x' + 'ab'.repeat(32),
            expiresAt: new Date(expiry).toISOString(),
            message: {
              actionId: id,
              protocolVersion: '1',
              ownerAccountUuid: context.ownerAccountUuid,
              walletUuid: context.walletUuid,
              tokenUuid: context.tokenUuid,
              orderUuid: context.orderUuid,
              wallet: context.walletAddress,
              nonce: '7',
              deadline: Math.floor(expiry / 1000).toString(),
              ...(purpose === 'modify'
                ? {
                    newQuantity: replacements.quantity,
                    newMinQuantity: replacements.minQuantity,
                    newPricePerShare: replacements.pricePerShare,
                  }
                : {}),
            },
          },
  };
}
