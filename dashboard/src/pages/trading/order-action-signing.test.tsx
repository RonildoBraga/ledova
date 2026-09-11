// @vitest-environment jsdom

import type { ReactNode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DataItem, extend, type DataItemMap } from '@keystonehq/bc-ur-registry';
import { UR, UREncoder } from '@ngraveio/bc-ur';
import { AnimatedQRCode } from '@keystonehq/animated-qr';
import { useQRScanner } from '@components/qr';
import { OrderActionFlow } from './components/OrderActionFlow';
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
import axios, { type InternalAxiosRequestConfig } from 'axios';
import { TypedDataEncoder, verifyTypedData } from 'ethers';
import {
  OrderAction,
  createOrderActionStore,
  type OrderActionContext,
  type OrderActionSnapshot,
  type Wallet,
  type TransferOrder,
} from '@ledova/shared';
import apiFixtures from '../../../../packages/shared/tests/fixtures/order-action-api.json';
import { memoryStorage, response, userUuid } from '../../../../packages/shared/tests/fixtures/order-submissions';

const fixtures = apiFixtures.fixtures as unknown as {
  purpose: 'cancel' | 'modify';
  context: OrderActionContext;
  snapshot: OrderActionSnapshot;
  request: Record<string, string>;
  signature: string;
}[];
afterEach(async () => {
  await cleanup();
  vi.restoreAllMocks();
});
it.each(fixtures.flatMap((fixture) => ['software', 'hardware'].map((mode) => ({ ...fixture, mode }))))(
  'signs actual API $purpose fixture with $mode and sends the same exact bound intent',
  async (fixture) => {
    const { purpose, context, snapshot, signature, mode } = fixture;
    const challenge = snapshot.challenge!;
    const nullableModification: Pick<TransferOrder, 'lastModifiedAt'> = { lastModifiedAt: null };
    expect(snapshot.order.lastModifiedAt).toBe(nullableModification.lastModifiedAt);
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse(challenge.expiresAt) - 60000);
    expect(TypedDataEncoder.hash(challenge.domain, challenge.types, challenge.message)).toBe(challenge.digest);
    expect(verifyTypedData(challenge.domain, challenge.types, challenge.message, signature)).toBe(
      apiFixtures.signer.address,
    );
    expect(
      verifyTypedData(
        challenge.domain,
        challenge.types,
        { ...challenge.message, actionId: 'different-action' },
        signature,
      ),
    ).not.toBe(apiFixtures.signer.address);
    expect(
      verifyTypedData({ ...challenge.domain, chainId: 11155111 }, challenge.types, challenge.message, signature),
    ).not.toBe(apiFixtures.signer.address);
    if (purpose === 'modify') {
      expect(String(snapshot.order.quantity)).not.toBe(snapshot.intent.modifications!.quantity);
      expect(
        verifyTypedData(
          challenge.domain,
          challenge.types,
          { ...challenge.message, newQuantity: '9007199254740992' },
          signature,
        ),
      ).not.toBe(apiFixtures.signer.address);
    }
    const memory = memoryStorage();
    const store = createOrderActionStore(memory.storage, () => snapshot.actionId);
    const calls: InternalAxiosRequestConfig[] = [];
    const api = axios.create();
    api.defaults.adapter = async (config) => {
      config.ledovaSubmissionGuard?.();
      calls.push(config);
      if (config.method === 'get') return response(config, JSON.stringify(context));
      if (config.url?.endsWith('/message/')) {
        expect(JSON.parse(config.data)).toEqual(fixture.request);
        expect(await store.list({ userUuid, ownerAccountUuid: context.ownerAccountUuid })).toHaveLength(1);
        return response(config, JSON.stringify(snapshot));
      }
      throw new Error('Synthetic lost response after signature submission');
    };
    const action = new OrderAction(
      { userUuid, ownerAccountUuid: context.ownerAccountUuid },
      context.orderUuid,
      purpose,
      {
        apiClient: api,
        store,
        isCurrent: () => true,
        onSettled: () => {},
        onRecordsChanged: () => {},
      },
    );
    const wallet = {
      uuid: context.walletUuid,
      userAccount: context.ownerAccountUuid,
      address: context.walletAddress,
      chain: 'ethereum',
      signingPreference: mode,
      derivationPath: apiFixtures.signer.derivationPath,
      masterFingerprint: '12345678',
      verificationStatus: 'PENDING',
    } as Wallet;
    render(<OrderActionFlow action={action} wallets={[wallet]} onClose={() => action.close()} />);
    await act(async () => {
      await action.load();
    });
    if (purpose === 'modify') {
      expect((screen.getByLabelText('New quantity') as HTMLInputElement).value).toBe('9007199254740993');
      fireEvent.change(screen.getByLabelText('New price per share'), { target: { value: '2.51' } });
    }
    fireEvent.click(screen.getByText(`Review ${purpose === 'cancel' ? 'cancellation' : 'change'}`));
    await waitFor(() => expect(action.getSnapshot().phase).toBe('ready'));
    if (mode === 'software') {
      fireEvent.click(screen.getByText('Continue to sign'));
      fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: apiFixtures.signer.mnemonic } });
      fireEvent.click(screen.getByText(`Sign ${purpose === 'cancel' ? 'cancellation' : 'change'}`));
    } else {
      fireEvent.click(screen.getByText('Continue to sign'));
      const cbor = vi.mocked(AnimatedQRCode).mock.calls.at(-1)![0].cbor;
      const request = extend.decodeToDataItem(Buffer.from(cbor, 'hex')).getData() as DataItemMap;
      expect(request[4]).toBe(challenge.domain.chainId);
      expect(JSON.parse((request[2] as Buffer).toString())).toEqual({
        domain: challenge.domain,
        types: challenge.types,
        message: challenge.message,
      });
      fireEvent.click(screen.getByText("I've signed it"));
      const scanner = vi
        .mocked(useQRScanner)
        .mock.calls.filter(([options]) => options.enabled)
        .at(-1)![0];
      const ur = new UREncoder(
        new UR(extend.encodeDataItem(new DataItem({ 2: Buffer.from(signature.slice(2), 'hex') })), 'eth-signature'),
        400,
      ).nextPart();
      await act(async () => {
        scanner.onScanSuccess(ur);
        scanner.onScanSuccess(ur);
      });
    }
    await waitFor(() => expect(action.getSnapshot().phase).toBe('error'));
    const executed = calls.filter((config) => config.method === 'post' && !config.url?.endsWith('/message/'));
    expect(executed).toHaveLength(1);
    const body = JSON.parse(executed[0]!.data);
    expect(body).toEqual({
      action_id: snapshot.actionId,
      owner_account_uuid: context.ownerAccountUuid,
      digest: challenge.digest,
      signature,
    });
    expect(verifyTypedData(challenge.domain, challenge.types, challenge.message, body.signature)).toBe(
      apiFixtures.signer.address,
    );
    expect(await store.list(action.owner)).toEqual([
      { version: 1, ...action.owner, orderUuid: context.orderUuid, purpose, actionId: snapshot.actionId },
    ]);
  },
);
