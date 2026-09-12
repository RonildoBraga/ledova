// @vitest-environment jsdom

import type { ReactNode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios, { type InternalAxiosRequestConfig } from 'axios';
import { DataItem, extend, type DataItemMap } from '@keystonehq/bc-ur-registry';
import { UR, UREncoder } from '@ngraveio/bc-ur';
import { AnimatedQRCode } from '@keystonehq/animated-qr';
import { Interface, keccak256 } from 'ethers';
import {
  SwapSettlement,
  createSwapSettlementStore,
  type SwapSettlementResponse,
  type SwapSettlementApprovalStatus,
  type SwapSettlementApprovalData,
  type Wallet,
} from '@ledova/shared';
import { useQRScanner } from '@components/qr';
import { swapSettlementCrypto, approvalTransactionForSigning } from '@services/swapSettlements';
import * as localSigner from '@utils/softwareWallet/localSigner';
import { SwapSettlementFlow } from './components/SwapSettlementFlow';
import apiFixture from '../../../../packages/shared/tests/fixtures/swap-settlement-api.json';
import { memoryStorage, response, userUuid } from '../../../../packages/shared/tests/fixtures/order-submissions';

vi.mock('@components/Modal', () => ({ Modal: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('@components/SeedPhraseInput', () => ({
  SeedPhraseInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <input aria-label="Synthetic seed" value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}));
vi.mock('@components/qr', () => ({
  useQRScanner: vi.fn(() => ({ error: null, stopScanner: vi.fn() })),
  QRScannerView: () => null,
}));
vi.mock('@keystonehq/animated-qr', () => ({ AnimatedQRCode: vi.fn(() => null) }));

const fixture = apiFixture.get_body as SwapSettlementResponse;
const identity = {
  orderUuid: fixture.orderUuid,
  swapUuid: fixture.swapUuid,
  ownerAccountUuid: fixture.ownerAccountUuid,
  walletUuid: fixture.walletUuid,
  settlementDigest: fixture.settlementDigest,
};
const owner = { userUuid, ownerAccountUuid: fixture.ownerAccountUuid };
const wallet: Wallet = {
  uuid: fixture.walletUuid,
  userAccount: fixture.ownerAccountUuid,
  address: apiFixture.addresses[0]!,
  chain: 'base',
  verificationStatus: 'VERIFIED',
  signingPreference: 'software',
  derivationPath: apiFixture.paths[0]!,
  masterFingerprint: '12345678',
  createdAt: fixture.swapOrder.createdAt,
  updatedAt: apiFixture.get_body.swapOrder.updatedAt,
  nativeBalance: '0',
  nativeMarketValue: '0',
  marketValue: '0',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => (resolve = done));
  return { promise, resolve };
}

function setup(needsApproval = false) {
  const memory = memoryStorage();
  const store = createSwapSettlementStore(memory.storage);
  const calls: InternalAxiosRequestConfig[] = [];
  const approval = {
    from: wallet.address,
    to: fixture.typedData.message.shareToken,
    data: new Interface(['function approve(address,uint256)']).encodeFunctionData('approve', [
      fixture.typedData.domain.verifyingContract,
      (1n << 256n) - 1n,
    ]),
    value: '0x0',
    gas: '0x186a0',
    gasPrice: '0x1',
    nonce: '0x0',
    chainId: '0x14a34',
  };
  const state = { current: true, lostSignature: false, loseApproval: false, needsApproval, submitted: '' };
  const api = axios.create();
  api.defaults.adapter = async (config) => {
    config.ledovaSubmissionGuard?.();
    calls.push(config);
    if (config.method === 'post') {
      const reminders = await store.list(owner);
      expect(reminders).toHaveLength(1);
      const body = JSON.parse(config.data);
      expect(body).toMatchObject({
        owner_account_uuid: identity.ownerAccountUuid,
        wallet_uuid: identity.walletUuid,
        settlement_digest: identity.settlementDigest,
      });
      if (config.url?.endsWith('/approval-broadcast/')) {
        expect(reminders[0]).toMatchObject({ kind: 'approval', txHash: keccak256(body.signed_transaction) });
        state.needsApproval = false;
        if (state.loseApproval) throw new Error('Synthetic lost approval response');
        return response(
          config,
          JSON.stringify({
            ...identity,
            userRole: 'seller',
            txHash: keccak256(body.signed_transaction),
            blockNumber: 7,
            gasUsed: 40000,
          }),
        );
      }
      state.submitted = body.signature;
      if (state.lostSignature) throw new Error('Synthetic lost signature response');
      return response(
        config,
        JSON.stringify(
          body.signature === apiFixture.signatures[0]
            ? apiFixture.seller_post_body
            : { ...fixture.swapOrder, buyerHasSigned: true, status: 'buyer_signed' },
        ),
      );
    }
    if (config.url?.endsWith('/approval-status/')) {
      const status: SwapSettlementApprovalStatus = {
        ...identity,
        userRole: 'seller',
        tokenAddress: approval.to,
        tokenSymbol: fixture.swapOrder.settlementContext.shareToken.symbol,
        requiredAmount: fixture.typedData.message.shareAmount,
        currentAllowance: state.needsApproval ? '0' : ((1n << 256n) - 1n).toString(),
        needsApproval: state.needsApproval,
        spender: fixture.typedData.domain.verifyingContract,
      };
      return response(config, JSON.stringify(status));
    }
    if (config.url?.endsWith('/approval-data/')) {
      const data: SwapSettlementApprovalData = {
        ...identity,
        userRole: 'seller',
        needsApproval: true,
        transaction: approval,
        description: 'Synthetic captured approval',
        tokenAddress: approval.to,
        tokenSymbol: fixture.swapOrder.settlementContext.shareToken.symbol,
        spender: fixture.typedData.domain.verifyingContract,
        amount: ((1n << 256n) - 1n).toString(),
        unlimited: true,
      };
      return response(config, JSON.stringify(data));
    }
    const signed = state.submitted === apiFixture.signatures[0];
    const swapOrder = signed
      ? apiFixture.seller_post_body
      : state.submitted
        ? { ...fixture.swapOrder, buyerHasSigned: true, status: 'buyer_signed' }
        : fixture.swapOrder;
    return response(config, JSON.stringify({ ...fixture, hasSigned: signed, canSign: !signed, swapOrder }));
  };
  const settlement = new SwapSettlement(
    owner,
    { ...identity, walletAddress: wallet.address },
    {
      apiClient: api,
      store,
      crypto: swapSettlementCrypto,
      isCurrent: () => state.current,
      onRecordsChanged: () => {},
      onUpdated: () => {},
    },
  );
  return { settlement, calls, store, memory, state, approval };
}

async function load(settlement: SwapSettlement) {
  await act(async () => {
    await settlement.load();
  });
  fireEvent.click(screen.getByText('Check token approval'));
  await waitFor(() => expect(settlement.getSnapshot().approvalStatus).not.toBeNull());
}

function enterSeed(kind: 'trade' | 'approval') {
  fireEvent.click(screen.getByText(kind === 'trade' ? 'Continue to sign' : 'Continue to approve'));
  fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: apiFixture.mnemonic } });
  fireEvent.click(screen.getByText(`Sign ${kind}`));
  expect(screen.queryByLabelText('Synthetic seed')).toBeNull();
}

function signatureUr(signature: string) {
  return new UREncoder(
    new UR(extend.encodeDataItem(new DataItem({ 2: Buffer.from(signature.slice(2), 'hex') })), 'eth-signature'),
    400,
  ).nextPart();
}

beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse(fixture.swapOrder.createdAt) + 5000);
});
afterEach(async () => {
  await cleanup();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

it('shows exact captured values and records the actual software signature after saving its identity', async () => {
  const { settlement, calls, store } = setup();
  render(<SwapSettlementFlow settlement={settlement} wallets={[wallet]} onClose={() => {}} />);
  await load(settlement);
  expect(screen.getByText(/Shares: 9007199254740993 DEP/)).toBeTruthy();
  expect(screen.getByText('Payment: 13510798882111489.50 TUSD')).toBeTruthy();
  enterSeed('trade');
  await waitFor(() => expect(settlement.getSnapshot().response?.hasSigned).toBe(true));
  await waitFor(() => expect(settlement.getSnapshot().phase).toBe('ready'));
  expect(calls.filter((call) => call.method === 'post')).toHaveLength(1);
  expect(JSON.parse(calls.find((call) => call.method === 'post')!.data).signature).toBe(apiFixture.signatures[0]);
  expect(await store.list(owner)).toEqual([]);
  expect(screen.getByText('Your signature is recorded. Trade status: seller_signed.')).toBeTruthy();
});

it.each(['close', 'wallet', 'owner', 'unmount'] as const)(
  'refuses a valid delayed software signature after %s retirement',
  async (retirement) => {
    const { settlement, calls, state, store } = setup();
    const signed = deferred<string>();
    const signer = vi.spyOn(localSigner, 'signEthereumTypedData').mockReturnValue(signed.promise);
    const view = render(<SwapSettlementFlow settlement={settlement} wallets={[wallet]} onClose={() => {}} />);
    await load(settlement);
    enterSeed('trade');
    await waitFor(() => expect(signer).toHaveBeenCalledOnce());
    if (retirement === 'close') fireEvent.click(screen.getByText('Close'));
    else if (retirement === 'wallet')
      view.rerender(
        <SwapSettlementFlow
          settlement={settlement}
          wallets={[{ ...wallet, masterFingerprint: '87654321' }]}
          onClose={() => {}}
        />,
      );
    else if (retirement === 'owner') state.current = false;
    else view.unmount();
    await act(async () => {
      signed.resolve(apiFixture.signatures[0]!);
      await signed.promise;
    });
    expect(calls.filter((call) => call.method === 'post')).toEqual([]);
    expect(await store.list(owner)).toEqual([]);
  },
);

it('recovers a lost signature response without signing or submitting it again', async () => {
  const { settlement, calls, store, state } = setup();
  state.lostSignature = true;
  render(<SwapSettlementFlow settlement={settlement} wallets={[wallet]} onClose={() => {}} />);
  await load(settlement);
  enterSeed('trade');
  await waitFor(() => expect(settlement.getSnapshot().phase).toBe('error'));
  expect(await store.list(owner)).toHaveLength(1);
  fireEvent.click(screen.getByText('Check saved status'));
  await waitFor(() => expect(settlement.getSnapshot().response?.hasSigned).toBe(true));
  expect(await store.list(owner)).toEqual([]);
  expect(calls.filter((call) => call.method === 'post')).toHaveLength(1);
});

it('keeps an unknown approval hash after allowance becomes sufficient and never rebroadcasts it', async () => {
  const { settlement, calls, store, state, approval } = setup(true);
  state.loseApproval = true;
  const signed = await localSigner.signEthereumTransaction(
    apiFixture.mnemonic,
    apiFixture.paths[0]!,
    approvalTransactionForSigning(approval),
  );
  render(<SwapSettlementFlow settlement={settlement} wallets={[wallet]} onClose={() => {}} />);
  await load(settlement);
  fireEvent.click(screen.getByText('Prepare approval'));
  await waitFor(() => expect(screen.getByText('This token approval has no spending limit.')).toBeTruthy());
  enterSeed('approval');
  await waitFor(() => expect(settlement.getSnapshot().phase).toBe('error'));
  expect(await store.list(owner)).toEqual([expect.objectContaining({ kind: 'approval', txHash: keccak256(signed) })]);
  fireEvent.click(screen.getByText('Check saved status'));
  await waitFor(() => expect(settlement.getSnapshot().phase).toBe('ready'));
  fireEvent.click(screen.getByText('Check token approval'));
  await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
  expect(screen.getByText(keccak256(signed))).toBeTruthy();
  expect(await store.list(owner)).toHaveLength(1);
  expect(calls.filter((call) => call.method === 'post')).toHaveLength(1);
});

it('refuses a valid approval signer response after closing the review', async () => {
  const { settlement, calls, store, approval } = setup(true);
  const raw = await localSigner.signEthereumTransaction(
    apiFixture.mnemonic,
    apiFixture.paths[0]!,
    approvalTransactionForSigning(approval),
  );
  const pending = deferred<string>();
  const signer = vi.spyOn(localSigner, 'signEthereumTransaction').mockReturnValue(pending.promise);
  render(<SwapSettlementFlow settlement={settlement} wallets={[wallet]} onClose={() => {}} />);
  await load(settlement);
  fireEvent.click(screen.getByText('Prepare approval'));
  await waitFor(() => expect(screen.getByText('Continue to approve')).toBeTruthy());
  enterSeed('approval');
  await waitFor(() => expect(signer).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByText('Close'));
  await act(async () => {
    pending.resolve(raw);
    await pending.promise;
  });
  expect(calls.filter((call) => call.method === 'post')).toEqual([]);
  expect(await store.list(owner)).toEqual([]);
});

it('encodes captured hardware values and relays a signature from either captured participant once', async () => {
  const { settlement, calls } = setup();
  render(
    <SwapSettlementFlow
      settlement={settlement}
      wallets={[{ ...wallet, signingPreference: 'hardware' }]}
      onClose={() => {}}
    />,
  );
  await load(settlement);
  fireEvent.click(screen.getByText('Continue to sign'));
  const request = extend
    .decodeToDataItem(Buffer.from(vi.mocked(AnimatedQRCode).mock.calls.at(-1)![0].cbor, 'hex'))
    .getData() as DataItemMap;
  expect(JSON.parse((request[2] as Buffer).toString())).toEqual(fixture.typedData);
  fireEvent.click(screen.getByText("I've signed it"));
  const scanner = vi
    .mocked(useQRScanner)
    .mock.calls.filter(([options]) => options.enabled)
    .at(-1)![0];
  await act(async () => {
    scanner.onScanSuccess(signatureUr(apiFixture.signatures[1]!));
    scanner.onScanSuccess(signatureUr(apiFixture.signatures[1]!));
  });
  await waitFor(() => expect(calls.filter((call) => call.method === 'post')).toHaveLength(1));
  await waitFor(() => expect(settlement.getSnapshot().phase).toBe('ready'));
  expect(settlement.getSnapshot().response?.swapOrder.buyerHasSigned).toBe(true);
  expect(JSON.parse(calls.find((call) => call.method === 'post')!.data)).toMatchObject({
    signature: apiFixture.signatures[1],
    signer_address: apiFixture.addresses[1],
  });
});

it('drops a queued valid hardware recovery after the selected device changes', async () => {
  const { settlement, calls } = setup();
  const selected = { ...wallet, signingPreference: 'hardware' as const };
  const view = render(<SwapSettlementFlow settlement={settlement} wallets={[selected]} onClose={() => {}} />);
  await load(settlement);
  fireEvent.click(screen.getByText('Continue to sign'));
  fireEvent.click(screen.getByText("I've signed it"));
  const recovered = deferred<string>();
  const recover = vi.spyOn(swapSettlementCrypto, 'recoverSigner').mockReturnValue(recovered.promise);
  const scanner = vi
    .mocked(useQRScanner)
    .mock.calls.filter(([options]) => options.enabled)
    .at(-1)![0];
  await act(async () => {
    scanner.onScanSuccess(signatureUr(apiFixture.signatures[0]!));
  });
  expect(recover).toHaveBeenCalledOnce();
  view.rerender(
    <SwapSettlementFlow
      settlement={settlement}
      wallets={[{ ...selected, derivationPath: apiFixture.paths[1]! }]}
      onClose={() => {}}
    />,
  );
  await act(async () => {
    recovered.resolve(wallet.address);
    await recovered.promise;
  });
  expect(calls.filter((call) => call.method === 'post')).toEqual([]);
});

it('discards the old QR result after Back and a new review while admitting the new scan', async () => {
  const { settlement, calls } = setup();
  render(
    <SwapSettlementFlow
      settlement={settlement}
      wallets={[{ ...wallet, signingPreference: 'hardware' }]}
      onClose={() => {}}
    />,
  );
  await load(settlement);
  fireEvent.click(screen.getByText('Continue to sign'));
  fireEvent.click(screen.getByText("I've signed it"));
  const oldScanner = vi
    .mocked(useQRScanner)
    .mock.calls.filter(([options]) => options.enabled)
    .at(-1)![0];
  const pending = deferred<string>();
  const recover = vi.spyOn(swapSettlementCrypto, 'recoverSigner').mockReturnValue(pending.promise);
  await act(async () => {
    oldScanner.onScanSuccess(signatureUr(apiFixture.signatures[0]!));
  });
  expect(recover).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByText('Back'));
  fireEvent.click(screen.getByText('Continue to sign'));
  fireEvent.click(screen.getByText("I've signed it"));
  const newScanner = vi
    .mocked(useQRScanner)
    .mock.calls.filter(([options]) => options.enabled)
    .at(-1)![0];
  recover.mockRestore();
  await act(async () => {
    pending.resolve(wallet.address);
    await pending.promise;
  });
  expect(calls.filter((call) => call.method === 'post')).toEqual([]);
  await act(async () => {
    oldScanner.onScanSuccess(signatureUr(apiFixture.signatures[0]!));
  });
  expect(calls.filter((call) => call.method === 'post')).toEqual([]);
  await act(async () => {
    newScanner.onScanSuccess(signatureUr(apiFixture.signatures[0]!));
  });
  await waitFor(() => expect(settlement.getSnapshot().response?.hasSigned).toBe(true));
  expect(calls.filter((call) => call.method === 'post')).toHaveLength(1);
});
