// @vitest-environment jsdom

import type { ReactNode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios, { type InternalAxiosRequestConfig } from 'axios';
import { DataItem, extend } from '@keystonehq/bc-ur-registry';
import { UR, UREncoder } from '@ngraveio/bc-ur';
import { SwapSettlement, createSwapSettlementStore, type SwapSettlementResponse, type Wallet } from '@ledova/shared';
import { swapSettlementCrypto } from '@services/swapSettlements';
import { SwapSettlementFlow } from './components/SwapSettlementFlow';
import fixture from '../../../../packages/shared/tests/fixtures/swap-settlement-api.json';
import { memoryStorage, response, userUuid } from '../../../../packages/shared/tests/fixtures/order-submissions';

vi.mock('@components/Modal', () => ({ Modal: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('@keystonehq/animated-qr', () => ({ AnimatedQRCode: () => null }));
const scans = vi.hoisted(() => [] as { success: (text: string) => void; stopped: boolean }[]);
vi.mock('html5-qrcode', () => ({
  Html5Qrcode: class {
    entry: { success: (text: string) => void; stopped: boolean } = { success: () => {}, stopped: false };
    static getCameras = async () => [{ id: 'synthetic-camera' }];
    getState() {
      return this.entry.stopped ? 1 : 2;
    }
    start(_id: string, _config: unknown, success: (text: string) => void) {
      this.entry.success = success;
      scans.push(this.entry);
      return Promise.resolve();
    }
    stop() {
      this.entry.stopped = true;
      return Promise.resolve();
    }
  },
}));

const captured = fixture.get_body as SwapSettlementResponse;
const identity = {
  orderUuid: captured.orderUuid,
  swapUuid: captured.swapUuid,
  ownerAccountUuid: captured.ownerAccountUuid,
  walletUuid: captured.walletUuid,
  settlementDigest: captured.settlementDigest,
};
const owner = { userUuid, ownerAccountUuid: identity.ownerAccountUuid };
const wallet: Wallet = {
  uuid: identity.walletUuid,
  userAccount: identity.ownerAccountUuid,
  address: fixture.addresses[0]!,
  chain: 'base',
  verificationStatus: 'VERIFIED',
  signingPreference: 'hardware',
  derivationPath: fixture.paths[0]!,
  masterFingerprint: '12345678',
  createdAt: captured.swapOrder.createdAt,
  updatedAt: fixture.get_body.swapOrder.updatedAt,
  nativeBalance: '0',
  nativeMarketValue: '0',
  marketValue: '0',
};

function setup() {
  const store = createSwapSettlementStore(memoryStorage().storage);
  const posts: InternalAxiosRequestConfig[] = [];
  const api = axios.create();
  api.defaults.adapter = async (config) => {
    config.ledovaSubmissionGuard?.();
    if (config.method === 'post') {
      expect(await store.list(owner)).toEqual([
        expect.objectContaining({ ...identity, kind: 'signature', signerAddress: wallet.address.toLowerCase() }),
      ]);
      expect(JSON.parse(config.data).signature).toBe(fixture.signatures[0]);
      posts.push(config);
      return response(config, JSON.stringify(fixture.seller_post_body));
    }
    if (config.url?.endsWith('/approval-status/'))
      return response(
        config,
        JSON.stringify({
          ...identity,
          userRole: 'seller',
          tokenAddress: captured.typedData.message.shareToken,
          tokenSymbol: captured.swapOrder.settlementContext.shareToken.symbol,
          requiredAmount: captured.typedData.message.shareAmount,
          currentAllowance: ((1n << 256n) - 1n).toString(),
          needsApproval: false,
          spender: captured.typedData.domain.verifyingContract,
        }),
      );
    return response(
      config,
      JSON.stringify({
        ...captured,
        hasSigned: posts.length > 0,
        canSign: posts.length === 0,
        swapOrder: posts.length ? fixture.seller_post_body : captured.swapOrder,
      }),
    );
  };
  const settlement = new SwapSettlement(
    owner,
    { ...identity, walletAddress: wallet.address },
    {
      apiClient: api,
      store,
      crypto: swapSettlementCrypto,
      isCurrent: () => true,
      onRecordsChanged() {},
      onUpdated() {},
    },
  );
  return { settlement, posts, store };
}

function signatureUr() {
  return new UREncoder(
    new UR(
      extend.encodeDataItem(new DataItem({ 2: Buffer.from(fixture.signatures[0]!.slice(2), 'hex') })),
      'eth-signature',
    ),
    400,
  ).nextPart();
}

beforeEach(() => {
  scans.length = 0;
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse(captured.swapOrder.createdAt) + 5000);
});
afterEach(async () => {
  await cleanup();
  vi.restoreAllMocks();
});

it.each([false, true])(
  'admits a fresh real-hook scan after reopening, with retired delivery %s',
  async (deliverOld) => {
    const { settlement, posts, store } = setup();
    render(<SwapSettlementFlow settlement={settlement} wallets={[wallet]} onClose={() => {}} />);
    await act(async () => settlement.load());
    fireEvent.click(screen.getByText('Check token approval'));
    await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
    fireEvent.click(screen.getByText('Continue to sign'));
    fireEvent.click(screen.getByText("I've signed it"));
    await waitFor(() => expect(scans).toHaveLength(1));
    const old = scans[0]!;
    fireEvent.click(screen.getByText('Back'));
    await waitFor(() => expect(old.stopped).toBe(true));
    fireEvent.click(screen.getByText('Continue to sign'));
    fireEvent.click(screen.getByText("I've signed it"));
    await waitFor(() => expect(scans).toHaveLength(2));
    if (deliverOld) {
      await act(async () => old.success(signatureUr()));
      expect(posts).toEqual([]);
      expect(scans[1]!.stopped).toBe(false);
    }
    await act(async () => scans[1]!.success(signatureUr()));
    await waitFor(() => expect(settlement.getSnapshot().response?.hasSigned).toBe(true));
    expect(posts).toHaveLength(1);
    expect(await store.list(owner)).toEqual([]);
  },
);
