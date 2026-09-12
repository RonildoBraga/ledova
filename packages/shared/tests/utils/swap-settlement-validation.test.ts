import type { SwapSettlementResponse } from '../../src/types';
import {
  hasSwapSettlementContext,
  selectSwapSettlementLookup,
  swapSettlementIdentity,
  validateSwapSettlementApprovalData,
  validateSwapSettlementApprovalResult,
  validateSwapSettlementResponse,
  validateSwapSettlementSignedApproval,
} from '../../src/utils/swap-settlement-validation';
import {
  approvalHash,
  settlementApproval,
  settlementCrypto,
  settlementOwner,
  settlementResponse,
} from '../fixtures/swap-settlements';

function wallet(response = settlementResponse()) {
  const side = response.swapOrder.settlementContext[response.userRole];
  return { uuid: side.walletUuid, userAccount: side.ownerAccountUuid, address: side.address };
}

test('buyer selects the original buy-order and captured exact display without preferring the sell-order', async () => {
  const value = settlementResponse('buyer');
  const selection = selectSwapSettlementLookup(value.swapOrder, settlementOwner, wallet(value));
  expect(selection.orderUuid).toBe(value.swapOrder.buyOrderUuid);
  expect(selection.orderUuid).not.toBe(value.swapOrder.sellOrderUuid);
  await expect(validateSwapSettlementResponse(value, selection, settlementCrypto(value))).resolves.toBeUndefined();
  expect(value.swapOrder.settlementContext.paymentAsset.pricingDecimals).toBe(2);
  expect(value.typedData.message.paymentAmount).toBe('1351079888211148950');
});

test('current wallet or account mismatch cannot choose another captured side', () => {
  const value = settlementResponse();
  expect(() =>
    selectSwapSettlementLookup(value.swapOrder, settlementOwner, {
      ...wallet(),
      userAccount: '20000000-0000-4000-8000-000000000009',
    }),
  ).toThrow();
  expect(() =>
    selectSwapSettlementLookup(value.swapOrder, settlementOwner, wallet(), value.swapOrder.buyOrderUuid),
  ).toThrow();
  expect(
    selectSwapSettlementLookup(value.swapOrder, settlementOwner, wallet(), value.swapOrder.sellOrderUuid).orderUuid,
  ).toBe(value.orderUuid);
});

test.each<[string, (value: SwapSettlementResponse) => void]>([
  [
    'echo account',
    (v) => {
      v.ownerAccountUuid = '20000000-0000-4000-8000-000000000009';
    },
  ],
  [
    'echo wallet',
    (v) => {
      v.walletUuid = v.swapOrder.settlementContext.buyer.walletUuid;
    },
  ],
  [
    'role',
    (v) => {
      v.userRole = 'buyer';
    },
  ],
  [
    'top typed data',
    (v) => {
      v.typedData.message.shareAmount = '1';
    },
  ],
  [
    'stored display',
    (v) => {
      v.swapOrder.shareTokenName = 'Replacement';
    },
  ],
  [
    'deadline',
    (v) => {
      v.swapOrder.expiresAt = '2026-01-01T00:00:00Z';
    },
  ],
  [
    'version downgrade',
    (v) => {
      Object.assign(v.swapOrder, { settlementProtocolVersion: 0, settlementContext: null });
    },
  ],
  [
    'numeric uint',
    (v) => {
      Object.assign(v.swapOrder.settlementContext.typedData.message, { shareAmount: Number('9007199254740993') });
    },
  ],
  [
    'extra signed field',
    (v) => {
      Object.assign(v.swapOrder.settlementContext.typedData.message, { other: '1' });
    },
  ],
  [
    'field ordering',
    (v) => {
      v.swapOrder.settlementContext.typedData.types.SwapOrder.reverse();
    },
  ],
  [
    'domain digest',
    (v) => {
      v.swapOrder.settlementContext.typedData.domain.chainId = '31337';
    },
  ],
  [
    'computed full digest',
    (v) => {
      v.swapOrder.settlementContext.digest = '0x' + 'ef'.repeat(32);
      v.swapOrder.settlementDigest = v.swapOrder.settlementContext.digest;
    },
  ],
  [
    'unsafe amount overflow',
    (v) => {
      v.swapOrder.settlementContext.typedData.message.paymentAmount = (1n << 256n).toString();
    },
  ],
])('rejects mismatched %s with the actual API response as positive control', async (_name, mutate) => {
  const good = settlementResponse();
  const identity = swapSettlementIdentity(good);
  await expect(validateSwapSettlementResponse(good, identity, settlementCrypto())).resolves.toBeUndefined();
  const bad = settlementResponse();
  mutate(bad);
  await expect(validateSwapSettlementResponse(bad, identity, settlementCrypto())).rejects.toThrow();
});

test('nullable original asset references and buyer precedence are preserved without rewriting null', async () => {
  const value = settlementResponse();
  value.swapOrder.settlementContext.seller.paymentAssetUuid = null;
  await expect(validateSwapSettlementResponse(value, value, settlementCrypto())).resolves.toBeUndefined();
  value.swapOrder.settlementContext.seller.paymentAssetUuid = '20000000-0000-4000-8000-000000000099';
  await expect(validateSwapSettlementResponse(value, value, settlementCrypto())).resolves.toBeUndefined();
  value.swapOrder.settlementContext.buyer.paymentAssetUuid = null;
  await expect(validateSwapSettlementResponse(value, value, settlementCrypto())).rejects.toThrow();
});

test('recovery cannot change original captured review or remove an observed signature', async () => {
  const known = settlementResponse().swapOrder;
  const changed = settlementResponse();
  changed.swapOrder.settlementContext.shareToken.name = 'Changed';
  changed.swapOrder.shareTokenName = 'Changed';
  await expect(validateSwapSettlementResponse(changed, changed, settlementCrypto(), known)).rejects.toThrow(
    /original review/,
  );
  known.sellerHasSigned = true;
  await expect(
    validateSwapSettlementResponse(settlementResponse(), settlementResponse(), settlementCrypto(), known),
  ).rejects.toThrow(/stored signature/);
});

test('legacy discriminator preserves version0 without manufacturing an immutable context', () => {
  const legacy = {
    ...settlementResponse().swapOrder,
    settlementProtocolVersion: 0 as const,
    settlementContext: null,
    settlementDigest: '',
  };
  expect(hasSwapSettlementContext(legacy)).toBe(false);
  expect(hasSwapSettlementContext(settlementResponse().swapOrder)).toBe(true);
  expect(hasSwapSettlementContext({ ...legacy, settlementProtocolVersion: 1 })).toBe(false);
});

test('prepared and decoded approval compare numeric hex meaning but preserve every signed transaction field', () => {
  const response = settlementResponse();
  const prepared = settlementApproval();
  validateSwapSettlementApprovalData(prepared, response);
  const inspected = {
    txHash: approvalHash,
    transaction: { ...prepared.transaction, nonce: '0x00', value: '0x00', chainId: '0x014a34' },
  };
  expect(() => validateSwapSettlementSignedApproval(inspected, prepared.transaction, response)).not.toThrow();
  for (const key of ['nonce', 'gas', 'gasPrice', 'value', 'chainId'] as const) {
    expect(() =>
      validateSwapSettlementSignedApproval(
        { ...inspected, transaction: { ...inspected.transaction, [key]: '0x2' } },
        prepared.transaction,
        response,
      ),
    ).toThrow();
  }
  for (const key of ['from', 'to', 'data'] as const) {
    expect(() =>
      validateSwapSettlementSignedApproval(
        { ...inspected, transaction: { ...inspected.transaction, [key]: '0x' + '12'.repeat(20) } },
        prepared.transaction,
        response,
      ),
    ).toThrow();
  }
});

test('only an exact scoped hash and complete200 receipt may confirm; matching503 remains uncertain', () => {
  const response = settlementResponse();
  const receipt = {
    ...swapSettlementIdentity(response),
    userRole: response.userRole,
    txHash: approvalHash,
    blockNumber: null,
    gasUsed: null,
  };
  expect(() => validateSwapSettlementApprovalResult(receipt, 200, response, approvalHash)).not.toThrow();
  expect(() =>
    validateSwapSettlementApprovalResult({ ...receipt, txHash: '0x' + 'ff'.repeat(32) }, 200, response, approvalHash),
  ).toThrow();
  expect(() =>
    validateSwapSettlementApprovalResult(
      { ...receipt, blockNumber: undefined } as unknown as typeof receipt,
      200,
      response,
      approvalHash,
    ),
  ).toThrow();
  const uncertain = {
    ...swapSettlementIdentity(response),
    userRole: response.userRole,
    txHash: approvalHash,
    code: 'swap_approval_unconfirmed' as const,
    detail: 'Unconfirmed',
  };
  expect(() => validateSwapSettlementApprovalResult(uncertain, 503, response, approvalHash)).not.toThrow();
  expect(() => validateSwapSettlementApprovalResult(uncertain, 200, response, approvalHash)).toThrow();
  expect(() =>
    validateSwapSettlementApprovalResult({ ...uncertain, blockNumber: 7 }, 503, response, approvalHash),
  ).toThrow();
});

test('locally recomputed digest rejects an internally consistent altered domain', async () => {
  const value = settlementResponse();
  value.typedData.domain.chainId = '31337';
  value.swapOrder.settlementContext.typedData.domain.chainId = '31337';
  await expect(validateSwapSettlementResponse(value, value, settlementCrypto())).rejects.toThrow(/signing digest/);
});
