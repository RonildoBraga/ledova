import axios, { type InternalAxiosRequestConfig } from 'axios';
import {
  getSwapSettlementContext,
  submitSwapSettlementSignature,
  getSwapSettlementApprovalStatus,
  getSwapSettlementApprovalData,
  broadcastSwapSettlementApproval,
} from '../../src/services/swap-settlement';
import {
  getOrderSwapData,
  submitOrderSwapSignature,
  getOrderSwapApprovalStatus,
  getOrderSwapApprovalData,
} from '../../src/services/trading';
import { swapSettlementIdentity } from '../../src/utils/swap-settlement-validation';
import { settlementFixture, settlementResponse } from '../fixtures/swap-settlements';
import { response } from '../fixtures/order-submissions';

test('every scoped service pins exact identity and carries its existing transport guard/config', async () => {
  const api = axios.create();
  const requests: InternalAxiosRequestConfig[] = [];
  api.defaults.adapter = async (config) => {
    requests.push(config);
    return response(config, {});
  };
  const identity = swapSettlementIdentity(settlementResponse());
  const guard = jest.fn();
  const config = {
    ledovaSubmissionGuard: guard,
    headers: { 'X-Test': 'preserved' },
    params: { swap_uuid: 'wrong', wallet_uuid: 'wrong' },
  };
  await getSwapSettlementContext(api, identity, config);
  await submitSwapSettlementSignature(
    api,
    identity,
    { signature: settlementFixture.signatures[0]!, signerAddress: settlementFixture.addresses[0]! },
    config,
  );
  await getSwapSettlementApprovalStatus(api, identity, config);
  await getSwapSettlementApprovalData(api, identity, config);
  await broadcastSwapSettlementApproval(api, identity, '0x0123', config);
  for (const request of requests) {
    expect(request.url).toContain(`/orders/${identity.orderUuid}/swap/`);
    expect(request.ledovaSubmissionGuard).toBe(guard);
    expect(request.headers['X-Test']).toBe('preserved');
    const data = request.method === 'get' ? request.params : JSON.parse(request.data);
    expect(data).toMatchObject({
      swap_uuid: identity.swapUuid,
      owner_account_uuid: identity.ownerAccountUuid,
      wallet_uuid: identity.walletUuid,
      settlement_digest: identity.settlementDigest,
    });
  }
  expect(requests[4]!.url).toMatch(/approval-broadcast\/$/);
  expect(JSON.parse(requests[4]!.data).signed_transaction).toBe('0x0123');
});

test('version0 service calls retain their original unqualified wallet-address and signature bodies', async () => {
  const api = axios.create();
  const requests: InternalAxiosRequestConfig[] = [];
  api.defaults.adapter = async (config) => {
    requests.push(config);
    return response(config, {});
  };
  const order = settlementResponse().orderUuid;
  const address = settlementFixture.addresses[0]!;
  await getOrderSwapData(api, order, { walletAddress: address });
  await submitOrderSwapSignature(api, order, { signature: settlementFixture.signatures[0]!, signerAddress: address });
  await getOrderSwapApprovalStatus(api, order, address);
  await getOrderSwapApprovalData(api, order, address);
  expect(requests.filter((request) => request.method === 'get').map((request) => request.params)).toEqual(
    Array(3).fill({ wallet_address: address }),
  );
  expect(JSON.parse(requests[1]!.data)).toEqual({
    signature: settlementFixture.signatures[0],
    signer_address: address,
  });
});
