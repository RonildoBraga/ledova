import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react-native';
import { EthSignRequest, ETHSignature } from '@keystonehq/bc-ur-registry-eth';
import { OrderActionModal } from './components/OrderActionModal';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import { QRDisplay, QRScanner } from '../../components/qr';
jest.mock('uuid', () => ({ v4: () => '70000000-0000-4000-8000-000000000001' }));
jest.mock('../../services/secureKeyStorage', () => ({ getSeedPhrase: jest.fn() }));
jest.mock('../../components/qr', () => ({ QRDisplay: jest.fn(() => null), QRScanner: jest.fn(() => null) }));
jest.mock('../../components/modal', () => {
  const { View, Text, Pressable } = jest.requireActual('react-native');
  return {
    CustomModal: ({
      children,
      onConfirm,
      confirmLabel,
      confirmDisabled,
    }: {
      children: React.ReactNode;
      onConfirm?: () => void;
      confirmLabel: string;
      confirmDisabled: boolean;
    }) => (
      <View>
        {children}
        {onConfirm && (
          <Pressable onPress={onConfirm} disabled={confirmDisabled}>
            <Text>{confirmLabel}</Text>
          </Pressable>
        )}
      </View>
    ),
  };
});
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
  jest.restoreAllMocks();
});
it.each(fixtures.flatMap((fixture) => ['software', 'hardware'].map((mode) => ({ ...fixture, mode }))))(
  'signs actual API $purpose fixture with $mode and sends the same exact bound intent',
  async (fixture) => {
    const { purpose, context, snapshot, signature, mode } = fixture;
    const challenge = snapshot.challenge!;
    const nullableModification: Pick<TransferOrder, 'lastModifiedAt'> = { lastModifiedAt: null };
    expect(snapshot.order.lastModifiedAt).toBe(nullableModification.lastModifiedAt);
    jest.spyOn(Date, 'now').mockReturnValue(Date.parse(challenge.expiresAt) - 60000);
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
    const view = await render(<OrderActionModal action={action} wallets={[wallet]} onClose={() => action.close()} />);
    await act(async () => {
      await action.load();
    });
    if (purpose === 'modify') {
      expect(view.getByLabelText('New quantity').props.value).toBe('9007199254740993');
      await fireEvent.changeText(view.getByLabelText('New price per share'), '2.51');
    }
    await fireEvent.press(view.getByText(`Review ${purpose === 'cancel' ? 'cancellation' : 'change'}`));
    await waitFor(() => expect(action.getSnapshot().phase).toBe('ready'));
    if (mode === 'software') {
      jest.mocked(getSeedPhrase).mockResolvedValueOnce(apiFixtures.signer.mnemonic);
      await fireEvent.press(view.getByText('Sign with biometric'));
    } else {
      await fireEvent.press(view.getByText('Show signing code'));
      const cbor = jest.mocked(QRDisplay).mock.calls.at(-1)![0].data;
      if (typeof cbor !== 'string') throw new Error('Expected encoded CBOR hex');
      const request = EthSignRequest.fromCBOR(Buffer.from(cbor, 'hex'));
      expect(request.getChainId()).toBe(challenge.domain.chainId);
      expect(JSON.parse(request.getSignData().toString())).toEqual({
        domain: challenge.domain,
        types: challenge.types,
        message: challenge.message,
      });
      await fireEvent.press(view.getByText("I've signed it"));
      const scanner = jest
        .mocked(QRScanner)
        .mock.calls.filter(([props]) => props.visible)
        .at(-1)![0];
      const ur = new ETHSignature(Buffer.from(signature.slice(2), 'hex')).toUREncoder(400).nextPart();
      await act(async () => {
        scanner.onScan(ur);
        scanner.onScan(ur);
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
