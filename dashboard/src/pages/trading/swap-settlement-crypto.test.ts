import { readFileSync } from 'node:fs';
import { Interface, Transaction, keccak256 } from 'ethers';
import { describe, expect, it } from 'vitest';
import type { SwapSettlementResponse } from '@ledova/shared';
import { approvalTransactionForSigning, exactSettlementAmount, swapSettlementCrypto } from '@services/swapSettlements';
import { deriveAddress, signEthereumTransaction, signEthereumTypedData } from '@utils/softwareWallet/localSigner';

const fixture = JSON.parse(
  readFileSync(new URL('../../../../packages/shared/tests/fixtures/swap-settlement-api.json', import.meta.url), 'utf8'),
) as {
  synthetic_only: boolean;
  get_body: SwapSettlementResponse;
  mnemonic: string;
  paths: [string, string];
  addresses: [string, string];
  signatures: [string, string];
  claim: { to_address: string; function_args: Record<string, unknown> };
};

describe('settlement signing against actual backend output', () => {
  it('preserves the backend digest and both participant signatures through the real client signer', async () => {
    expect(fixture.synthetic_only).toBe(true);
    const response = fixture.get_body;
    const typed = response.typedData;
    expect(await swapSettlementCrypto.digestTypedData(typed)).toBe(response.settlementDigest);
    for (const index of [0, 1] as const) {
      expect(deriveAddress(fixture.mnemonic, fixture.paths[index])).toBe(fixture.addresses[index]);
      const signature = await signEthereumTypedData(
        fixture.mnemonic,
        fixture.paths[index],
        typed.domain,
        { SwapOrder: typed.types.SwapOrder },
        { ...typed.message },
      );
      expect(signature).toBe(fixture.signatures[index]);
      expect(await swapSettlementCrypto.recoverSigner(typed, signature)).toBe(fixture.addresses[index]);
    }
    for (const [field, value] of Object.entries(typed.message)) expect(fixture.claim.function_args[field]).toBe(value);
    expect(fixture.claim.to_address).toBe(typed.domain.verifyingContract);
    expect(fixture.claim.function_args.settlement).toMatchObject({
      digest: response.settlementDigest,
      domain: typed.domain,
    });
  });

  it('does not reuse the old signature under different exact amounts, nonce, deadline or domain', async () => {
    const typed = fixture.get_body.typedData;
    for (const field of ['shareAmount', 'paymentAmount', 'nonce', 'deadline'] as const) {
      const changed = {
        ...typed,
        message: { ...typed.message, [field]: (BigInt(typed.message[field]) + 1n).toString() },
      };
      expect(await swapSettlementCrypto.digestTypedData(changed)).not.toBe(fixture.get_body.settlementDigest);
      expect(await swapSettlementCrypto.recoverSigner(changed, fixture.signatures[0])).not.toBe(fixture.addresses[0]);
    }
    const changed = { ...typed, domain: { ...typed.domain, chainId: '11155111' } };
    expect(await swapSettlementCrypto.digestTypedData(changed)).not.toBe(fixture.get_body.settlementDigest);
  });

  it('displays captured large values exactly when ordinary JSON numbers lose precision', () => {
    const response = fixture.get_body;
    const context = response.swapOrder.settlementContext;
    expect(BigInt(response.swapOrder.shareAmount).toString()).not.toBe(response.typedData.message.shareAmount);
    expect(exactSettlementAmount(response.typedData.message.shareAmount, context.shareToken.decimals)).toBe(
      '9007199254740993',
    );
    expect(
      exactSettlementAmount(response.typedData.message.paymentAmount, context.paymentAsset.deploymentDecimals),
    ).toBe('13510798882111489.50');
    expect(exactSettlementAmount('1', 2)).toBe('0.01');
    expect(() => exactSettlementAmount('9007199254740993.0', 0)).toThrow();
  });

  it('decodes the signed approval rather than substituting the prepared transaction', async () => {
    const context = fixture.get_body.swapOrder.settlementContext;
    const approval = {
      from: fixture.addresses[0],
      to: context.shareToken.address,
      data: new Interface(['function approve(address,uint256)']).encodeFunctionData('approve', [
        context.typedData.domain.verifyingContract,
        (1n << 256n) - 1n,
      ]),
      value: '0x0',
      gas: '0x186a0',
      gasPrice: '0x1',
      nonce: '0x0',
      chainId: '0x14a34',
    };
    const signed = await signEthereumTransaction(
      fixture.mnemonic,
      fixture.paths[0],
      approvalTransactionForSigning(approval),
    );
    const decoded = await swapSettlementCrypto.inspectSignedApproval(signed);
    expect(decoded.txHash).toBe(keccak256(signed));
    expect(decoded.transaction.from).toBe(approval.from);
    expect(decoded.transaction.to.toLowerCase()).toBe(approval.to.toLowerCase());
    expect(decoded.transaction.data).toBe(approval.data);
    for (const field of ['value', 'gas', 'gasPrice', 'nonce', 'chainId'] as const)
      expect(BigInt(decoded.transaction[field])).toBe(BigInt(approval[field]));
    const other = await signEthereumTransaction(
      fixture.mnemonic,
      fixture.paths[1],
      approvalTransactionForSigning({ ...approval, nonce: '0x1' }),
    );
    const different = await swapSettlementCrypto.inspectSignedApproval(other);
    expect(different.transaction.from).toBe(fixture.addresses[1]);
    expect(BigInt(different.transaction.nonce)).toBe(1n);
    expect(different.txHash).not.toBe(decoded.txHash);
    expect(() => swapSettlementCrypto.inspectSignedApproval(Transaction.from(signed).unsignedSerialized)).toThrow();
    expect(() => approvalTransactionForSigning({ ...approval, nonce: '9007199254740993' })).toThrow();
  });
});
