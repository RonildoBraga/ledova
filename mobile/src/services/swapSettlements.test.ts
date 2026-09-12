import { EthSignRequest, ETHSignature } from '@keystonehq/bc-ur-registry-eth';
import { HDNodeWallet, Transaction, TypedDataEncoder } from 'ethers';
import { validateSwapSettlementResponse } from '@ledova/shared';
import fixture from '../../../packages/shared/tests/fixtures/swap-settlement-api.json';
import { settlementApproval, settlementResponse } from '../../../packages/shared/tests/fixtures/swap-settlements';
import {
  decodeSettlementApproval,
  encodeSettlementApproval,
  settlementApprovalTransaction,
  swapSettlementCrypto,
} from './swapSettlements';
import { signEthereumTransaction, signEthereumTypedData } from '../utils/softwareWallet/localSigner';
import { encodeEthereumTypedData } from '../utils/keystone/urEncoder';

jest.mock('uuid', () => ({ v4: () => '70000000-0000-4000-8000-000000000001' }));
const typed = settlementResponse().typedData;
const wallet = {
  address: HDNodeWallet.fromPhrase(fixture.mnemonic, undefined, fixture.paths[0]).address,
  derivationPath: fixture.paths[0],
  masterFingerprint: '12345678',
};

it('agrees with the actual backend full digest, both mobile software signatures, exact claim and UR bytes', async () => {
  expect(await swapSettlementCrypto.digestTypedData(typed)).toBe(fixture.get_body.settlementDigest);
  expect(TypedDataEncoder.hashStruct('SwapOrder', { SwapOrder: typed.types.SwapOrder }, typed.message).slice(2)).toBe(
    fixture.get_body.swapOrder.orderHash,
  );
  for (const index of [0, 1]) {
    const signature = await signEthereumTypedData(
      fixture.mnemonic,
      fixture.paths[index],
      typed.domain,
      { SwapOrder: typed.types.SwapOrder },
      typed.message,
    );
    expect(signature).toBe(fixture.signatures[index]);
    expect(await swapSettlementCrypto.recoverSigner(typed, signature)).toBe(fixture.addresses[index]);
    const qr = encodeEthereumTypedData(fixture.addresses[index], typed, fixture.paths[index], '12345678', 84532)!;
    const decoded = EthSignRequest.fromCBOR(qr.cbor);
    expect(JSON.parse(decoded.getSignData().toString('utf8'))).toEqual(typed);
  }
  expect(typed.message.shareAmount).toBe('9007199254740993');
  expect(fixture.claim.function_args).toEqual(
    expect.objectContaining({ shareAmount: typed.message.shareAmount, deadline: typed.message.deadline }),
  );
});

it.each(['shareAmount', 'paymentAmount', 'nonce', 'deadline'] as const)('refuses changed signed %s', async (field) => {
  const response = settlementResponse();
  response.swapOrder.settlementContext.typedData.message[field] = (BigInt(typed.message[field]) + 1n).toString();
  await expect(validateSwapSettlementResponse(response, response, swapSettlementCrypto)).rejects.toThrow();
});

it('encodes and reconstructs exact approval bytes with large gas-price and preserves the computed signed hash', async () => {
  const transaction = { ...settlementApproval().transaction, gasPrice: '0x20000000000001' };
  const input = settlementApprovalTransaction(transaction);
  const signed = await signEthereumTransaction(fixture.mnemonic, fixture.paths[0], input);
  const decoded = Transaction.from(signed);
  const code = encodeSettlementApproval(transaction, wallet);
  const request = EthSignRequest.fromCBOR(Buffer.from(code, 'hex'));
  expect(request.getSignData().toString('hex')).toBe(Transaction.from(input).unsignedSerialized.slice(2));
  const qr = new ETHSignature(Buffer.from(decoded.signature!.serialized.slice(2), 'hex')).toUREncoder(1000).nextPart();
  expect(decodeSettlementApproval(qr, transaction)).toBe(signed);
  const inspected = await swapSettlementCrypto.inspectSignedApproval(signed);
  expect(inspected.txHash).toBe(decoded.hash);
  expect(BigInt(inspected.transaction.gasPrice)).toBe(9007199254740993n);
});

it('refuses unsafe numeric-only hardware chain and nonce APIs without rounding', () => {
  const transaction = settlementApproval().transaction;
  expect(() => encodeSettlementApproval({ ...transaction, chainId: '0x20000000000001' }, wallet)).toThrow();
  expect(() => settlementApprovalTransaction({ ...transaction, nonce: '0x20000000000001' })).toThrow();
});
