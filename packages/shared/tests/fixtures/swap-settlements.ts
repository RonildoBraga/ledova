import type { SwapSettlementApprovalData, SwapSettlementCrypto, SwapSettlementResponse } from '../../src/types';
import fixture from './swap-settlement-api.json';

export const settlementFixture = fixture;
export const settlementOwner = {
  userUuid: '10000000-0000-4000-8000-000000000001',
  ownerAccountUuid: fixture.get_body.ownerAccountUuid,
};
export const settlementNow = Date.parse(fixture.get_body.swapOrder.createdAt) + 1000;
export const approvalHash = '0x' + 'ab'.repeat(32);
export const approvalRaw = '0x012345';

export function settlementResponse(role: 'seller' | 'buyer' = 'seller'): SwapSettlementResponse {
  const response = JSON.parse(JSON.stringify(fixture.get_body)) as SwapSettlementResponse;
  const party = response.swapOrder.settlementContext[role];
  response.userRole = role;
  response.orderUuid = party.orderUuid;
  response.walletUuid = party.walletUuid;
  response.ownerAccountUuid = party.ownerAccountUuid;
  return response;
}

export function settlementApproval(
  response = settlementResponse(),
): Extract<SwapSettlementApprovalData, { needsApproval: true }> {
  const context = response.swapOrder.settlementContext;
  const token = response.userRole === 'seller' ? context.shareToken.address : context.paymentAsset.deploymentAddress;
  const symbol = response.userRole === 'seller' ? context.shareToken.symbol : context.paymentAsset.symbol;
  const spender = response.typedData.domain.verifyingContract;
  return {
    swapUuid: response.swapUuid,
    orderUuid: response.orderUuid,
    ownerAccountUuid: response.ownerAccountUuid,
    walletUuid: response.walletUuid,
    settlementDigest: response.settlementDigest,
    userRole: response.userRole,
    needsApproval: true,
    tokenAddress: token,
    tokenSymbol: symbol,
    spender,
    amount: ((1n << 256n) - 1n).toString(),
    unlimited: true,
    description: 'Synthetic approval',
    transaction: {
      from: context[response.userRole].address,
      to: token,
      data: `0x095ea7b3${spender.slice(2).toLowerCase().padStart(64, '0')}${'f'.repeat(64)}`,
      value: '0x0',
      gas: '0x186a0',
      gasPrice: '0x1',
      nonce: '0x0',
      chainId: '0x14a34',
    },
  };
}

export function settlementCrypto(response = settlementResponse()): SwapSettlementCrypto {
  return {
    digestTypedData: jest.fn((data) =>
      JSON.stringify(data) === JSON.stringify(fixture.get_body.typedData)
        ? fixture.get_body.settlementDigest
        : '0x' + 'ff'.repeat(32),
    ),
    recoverSigner: jest.fn((_data, signature) => {
      const index = fixture.signatures.indexOf(signature);
      if (index < 0) throw new Error('Synthetic wrong signature');
      return fixture.addresses[index]!;
    }),
    inspectSignedApproval: jest.fn(() => ({
      txHash: approvalHash,
      transaction: settlementApproval(response).transaction,
    })),
  };
}
