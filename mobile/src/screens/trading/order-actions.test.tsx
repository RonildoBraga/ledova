import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import {
  ApiClientProvider,
  AUTH_QUERY_KEY,
  USER_PREFERENCES_QUERY_KEY,
  TRADING_ENDPOINTS,
  type OrderActionContext,
  type OrderActionSnapshot,
  type TransferOrder,
} from '@ledova/shared';
import { EthSignRequest, ETHSignature } from '@keystonehq/bc-ur-registry-eth';
import { QRDisplay, QRScanner } from '../../components/qr';
import { TradingScreen } from './index';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import { signEthereumTypedData } from '../../utils/softwareWallet/localSigner';
import { orderActionStore } from '../../services/orderActions';
import { invalidateSessionScope } from '../../services/sessionScope';
import {
  accountUuid,
  deferred,
  otherAccountUuid,
  owner,
  response,
  userUuid,
  wallet,
  walletUuid,
} from '../../../../packages/shared/tests/fixtures/order-submissions';
import {
  actionContext,
  actionId,
  actionSnapshot,
  largeMinimum,
  largeQuantity,
  orderUuid,
  otherOrderUuid,
  otherActionId,
} from '../../../../packages/shared/tests/fixtures/order-actions';

jest.mock('@react-navigation/native', () => ({
  useFocusEffect: (callback: () => () => void) => {
    const React = jest.requireActual('react');
    React.useEffect(callback, [callback]);
  },
}));
jest.mock('uuid', () => ({ v4: () => '70000000-0000-4000-8000-000000000001' }));
jest.mock('expo-crypto', () => ({ randomUUID: jest.fn() }));
jest.mock('../../services/secureKeyStorage', () => ({ getSeedPhrase: jest.fn() }));
jest.mock('../../utils/softwareWallet/localSigner', () => ({ signEthereumTypedData: jest.fn() }));
jest.mock('../../components/qr', () => ({ QRDisplay: jest.fn(() => null), QRScanner: jest.fn(() => null) }));
jest.mock('../../components/modal', () => {
  const { View, Text, Pressable } = jest.requireActual('react-native');
  return {
    CustomModal: jest.fn(
      ({
        visible,
        children,
        onClose,
        onConfirm,
        confirmLabel,
        confirmDisabled,
      }: {
        visible: boolean;
        children: React.ReactNode;
        onClose: () => void;
        onConfirm?: () => void;
        confirmLabel?: string;
        confirmDisabled?: boolean;
      }) =>
        visible ? (
          <View>
            {children}
            <Pressable onPress={onClose}>
              <Text>Dismiss window</Text>
            </Pressable>
            {onConfirm && (
              <Pressable disabled={confirmDisabled} onPress={onConfirm}>
                <Text>{confirmLabel}</Text>
              </Pressable>
            )}
          </View>
        ) : null,
    ),
  };
});
jest.mock('./components/MarketList', () => ({ MarketList: () => null }));
jest.mock('./components/OrdersCard', () => {
  const { Pressable, Text } = jest.requireActual('react-native');
  const f = jest.requireActual('../../../../packages/shared/tests/fixtures/order-actions');
  return {
    OrdersCard: ({
      onCancelOrder,
      onEditOrder,
    }: {
      onCancelOrder: (uuid: string) => void;
      onEditOrder: (order: TransferOrder) => void;
    }) => (
      <>
        <Pressable onPress={() => onCancelOrder(f.orderUuid)}>
          <Text>Cancel synthetic order</Text>
        </Pressable>
        <Pressable
          onPress={() =>
            onEditOrder(f.actionSnapshot('modify', 'pending', f.actionContext(f.largeQuantity, f.largeMinimum)).order)
          }
        >
          <Text>Change synthetic order</Text>
        </Pressable>
        <Pressable onPress={() => onEditOrder({ ...f.actionSnapshot().order, uuid: f.otherOrderUuid })}>
          <Text>Change other order</Text>
        </Pressable>
      </>
    ),
  };
});
jest.mock('./components/OrderDetailModal', () => ({ OrderDetailModal: () => null }));
jest.mock('./components/SwapSigningModal', () => ({ SwapSigningModal: () => null }));
jest.mock('./hooks/useTradingEvents', () => ({ useTradingEvents: () => {} }));
jest.mock('./useAtomicSwaps', () => ({ useSwapOrdersMulti: () => ({ data: [], refetch: jest.fn() }) }));
jest.mock('./useTrading', () => {
  const f = jest.requireActual('../../../../packages/shared/tests/fixtures/order-submissions');
  const tokens = [{ uuid: f.tokenUuid, name: 'Synthetic', symbol: 'SYN', lastPrice: '12.50' }];
  return {
    useShareTokens: () => ({ data: tokens, refetch: jest.fn() }),
    useInvestorEligibilityQuery: () => ({ data: { isEligible: true } }),
    useUserTradingWallets: () => ({
      wallets: [f.wallet],
      actionWallets: [f.wallet],
      walletAddresses: [f.wallet.address],
    }),
    useWalletsWhitelistStatus: () => ({
      isWhitelisted: () => true,
      getStatus: () => ({ status: 'whitelisted' }),
      isLoading: false,
    }),
    useOrderBook: () => ({ data: null }),
    useAllWalletTokenBalances: () => ({ getWalletsWithHoldings: () => [], refetch: jest.fn() }),
    useAllUserOrders: () => ({ orders: [], refetch: jest.fn() }),
  };
});

const endpoints = TRADING_ENDPOINTS.ORDERS;
let client: QueryClient;
let api = axios.create();
let requests: InternalAxiosRequestConfig[];
let context: OrderActionContext;
let stored: Map<string, OrderActionSnapshot>;
let handler: (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>;
const copy = <T,>(data: T): T => JSON.parse(JSON.stringify(data));
function setAccount(account = accountUuid) {
  client.setQueryData(AUTH_QUERY_KEY, { data: { valid: true } });
  client.setQueryData(USER_PREFERENCES_QUERY_KEY, {
    data: { userProfile: userUuid, selectedAccount: { uuid: account } },
  });
}
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <ApiClientProvider client={api}>{children}</ApiClientProvider>
    </QueryClientProvider>
  );
}
function messagePosts() {
  return requests.filter((config) => config.method === 'post' && config.url?.endsWith('/message/'));
}
function executes() {
  return requests.filter((config) => config.method === 'post' && !config.url?.endsWith('/message/'));
}
function fail(config: InternalAxiosRequestConfig, data: unknown, status: number): never {
  throw new AxiosError(
    'Synthetic response',
    String(status),
    config,
    undefined,
    response(config, JSON.stringify(data), status),
  );
}
async function ordinary(config: InternalAxiosRequestConfig): Promise<AxiosResponse> {
  if (config.url?.endsWith('/action-context/'))
    return response(config, { ...context, orderUuid: config.url.split('/').at(-3) });
  const body = config.data ? JSON.parse(config.data) : null;
  const id = body?.action_id ?? config.url!.split('/').at(-2);
  if (config.method === 'get') {
    const found = stored.get(id);
    if (!found) return fail(config, { detail: 'Not found.' }, 404);
    return response(config, { ...copy(found), challenge: null });
  }
  const purpose = config.url!.includes('/cancel/') ? 'cancel' : 'modify';
  if (config.url?.endsWith('/message/')) {
    const found = stored.get(id);
    const data =
      found ??
      actionSnapshot(
        purpose,
        'pending',
        copy(context),
        purpose === 'modify'
          ? { quantity: body.new_quantity, minQuantity: body.new_min_quantity, pricePerShare: body.new_price_per_share }
          : undefined,
        id,
      );
    stored.set(id, copy(data));
    return response(config, data);
  }
  const found = stored.get(id)!;
  const applied = {
    ...copy(found),
    status: 'applied' as const,
    challenge: null,
    result: actionSnapshot(
      purpose,
      'applied',
      { ...context, currentValues: found.review.currentValues },
      found.intent.modifications ?? undefined,
      id,
    ).result,
    order: { ...found.order, status: 'cancelled' as const, pricePerShare: '15.00' },
  };
  stored.set(id, copy(applied));
  return response(config, applied);
}
type Screen = Awaited<ReturnType<typeof render>>;
const nativeSet = jest.mocked(AsyncStorage.setItem).getMockImplementation()!;
async function begin(view: Screen, purpose: 'cancel' | 'modify' = 'modify') {
  await fireEvent.press(view.getByText(purpose === 'cancel' ? 'Cancel synthetic order' : 'Change synthetic order'));
  await waitFor(() =>
    expect(view.getByText(`Review ${purpose === 'cancel' ? 'cancellation' : 'change'}`)).toBeTruthy(),
  );
  if (purpose === 'modify') await fireEvent.changeText(view.getByLabelText('New price per share'), '14.00');
  await fireEvent.press(view.getByText(`Review ${purpose === 'cancel' ? 'cancellation' : 'change'}`));
  await waitFor(() =>
    expect(
      view.getByText(wallet.signingPreference === 'software' ? 'Sign with biometric' : 'Show signing code'),
    ).toBeTruthy(),
  );
}
beforeEach(async () => {
  jest.clearAllMocks();
  jest.mocked(AsyncStorage.setItem).mockImplementation(nativeSet);
  await AsyncStorage.clear();
  wallet.uuid = walletUuid;
  wallet.signingPreference = 'software';
  wallet.verificationStatus = 'VERIFIED';
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  setAccount();
  context = actionContext();
  stored = new Map();
  requests = [];
  api = axios.create();
  handler = ordinary;
  api.defaults.adapter = async (config) => {
    config.ledovaSubmissionGuard?.();
    requests.push(config);
    const reply = await handler(config);
    return { ...reply, data: JSON.stringify(reply.data) };
  };
  jest.mocked(Crypto.randomUUID).mockReset().mockReturnValueOnce(actionId).mockReturnValueOnce(otherActionId);
  jest.mocked(getSeedPhrase).mockResolvedValue('synthetic seed input');
  jest.mocked(signEthereumTypedData).mockResolvedValue('synthetic-signature');
});
afterEach(async () => {
  await cleanup();
  client.clear();
  jest.restoreAllMocks();
});

it('first price-only modification keeps exact context values despite the rounded numeric order DTO', async () => {
  context = actionContext(largeQuantity, largeMinimum);
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(view.getByText('Change synthetic order'));
  await waitFor(() => expect(view.getByLabelText('New quantity').props.value).toBe(largeQuantity));
  expect(view.getByLabelText('New minimum fill').props.value).toBe(largeMinimum);
  expect(await orderActionStore.list(owner)).toHaveLength(0);
  await fireEvent.changeText(view.getByLabelText('New price per share'), '14.00');
  await fireEvent.press(view.getByText('Review change'));
  await waitFor(() => expect(view.getByText(`New quantity: ${largeQuantity} shares`)).toBeTruthy());
  expect(JSON.parse(messagePosts()[0]!.data)).toEqual({
    action_id: actionId,
    owner_account_uuid: accountUuid,
    new_quantity: largeQuantity,
    new_min_quantity: largeMinimum,
    new_price_per_share: '14.00',
  });
  expect(await orderActionStore.list(owner)).toEqual([
    { version: 1, ...owner, actionId, orderUuid, purpose: 'modify' },
  ]);
  await fireEvent.press(view.getByText('Sign with biometric'));
  await waitFor(() => expect(view.getByText('Action recorded')).toBeTruthy());
  expect(jest.mocked(signEthereumTypedData).mock.calls[0]![4]).toMatchObject({
    newQuantity: largeQuantity,
    newMinQuantity: largeMinimum,
    newPricePerShare: '14.00',
    actionId,
  });
  expect(executes()).toHaveLength(1);
  expect(await orderActionStore.list(owner)).toHaveLength(0);
});

it('cancels with the scoped action ID and no create submission', async () => {
  const view = await render(<TradingScreen />, { wrapper });
  await begin(view, 'cancel');
  await fireEvent.press(view.getByText('Sign with biometric'));
  await waitFor(() =>
    expect(view.getByText('This cancellation changed the order from open to cancelled.')).toBeTruthy(),
  );
  expect(JSON.parse(messagePosts()[0]!.data)).toEqual({ action_id: actionId, owner_account_uuid: accountUuid });
  expect(JSON.parse(executes()[0]!.data)).toEqual({
    action_id: actionId,
    owner_account_uuid: accountUuid,
    digest: '0x' + 'ab'.repeat(32),
    signature: 'synthetic-signature',
  });
  expect(requests.some((request) => request.url === endpoints.CREATE)).toBe(false);
});

it('a rejected preparation can remove its reminder and review a new change after restart', async () => {
  context = actionContext('10', '1');
  handler = async (config) => {
    const reply = await ordinary(config);
    if (config.url === endpoints.MODIFY_MESSAGE(orderUuid) && JSON.parse(config.data).action_id === actionId) {
      context.currentValues.filledQuantity = '5';
      context.currentValues.remainingQuantity = '5';
      return fail(config, { detail: 'New quantity must exceed the filled amount.' }, 400);
    }
    return reply;
  };
  const first = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(first.getByText('Change synthetic order'));
  await first.findByLabelText('New quantity');
  await fireEvent.changeText(first.getByLabelText('New quantity'), '4');
  await fireEvent.press(first.getByText('Review change'));
  await first.findByText('New quantity must exceed the filled amount.');
  expect(await orderActionStore.list(owner)).toHaveLength(1);
  await first.unmount();
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(await view.findByText('Check change 1'));
  await view.findByText('New quantity must exceed the filled amount.');
  expect(stored.get(actionId)?.status).toBe('pending');
  expect(await orderActionStore.list(owner)).toHaveLength(1);
  await fireEvent.press(view.getByRole('button', { name: 'Remove saved reminder' }));
  await waitFor(() => expect(view.getByLabelText('New quantity').props.value).toBe('10'));
  expect(view.getByText('Filled: 5 shares')).toBeTruthy();
  expect(await orderActionStore.list(owner)).toHaveLength(0);
  expect(stored.get(actionId)?.intent.modifications?.quantity).toBe('4');
  expect(stored.get(actionId)?.status).toBe('pending');
  await fireEvent.changeText(view.getByLabelText('New quantity'), '6');
  await fireEvent.press(view.getByText('Review change'));
  await view.findByText('Sign with biometric');
  expect(messagePosts().map((request) => JSON.parse(request.data).action_id)).toEqual([
    actionId,
    actionId,
    otherActionId,
  ]);
  expect(await orderActionStore.list(owner)).toEqual([
    { version: 1, ...owner, actionId: otherActionId, orderUuid, purpose: 'modify' },
  ]);
  expect(executes()).toHaveLength(0);
  expect(signEthereumTypedData).not.toHaveBeenCalled();
});

it('removes a confirmed reminder from the parent list after its modal closes during deletion', async () => {
  handler = async (config) => {
    const reply = await ordinary(config);
    if (config.url === endpoints.MODIFY_MESSAGE(orderUuid))
      return fail(config, { detail: 'This synthetic change is no longer valid.' }, 400);
    return reply;
  };
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(view.getByText('Change synthetic order'));
  await view.findByLabelText('New quantity');
  await fireEvent.press(view.getByText('Review change'));
  await view.findByText('This synthetic change is no longer valid.');
  await view.findByText('Check change 1');
  const pause = deferred<void>();
  const originalRemove = orderActionStore.remove;
  const remove = jest.spyOn(orderActionStore, 'remove').mockImplementation(async (record) => {
    await pause.promise;
    return originalRemove(record);
  });
  await fireEvent.press(view.getByRole('button', { name: 'Remove saved reminder' }));
  expect(remove).toHaveBeenCalledTimes(1);
  await fireEvent.press(view.getByText('Dismiss window'));
  expect(view.getByText('Check change 1')).toBeTruthy();
  expect(await orderActionStore.list(owner)).toHaveLength(1);
  const count = requests.length;
  await act(async () => {
    pause.resolve();
    await pause.promise;
  });
  await waitFor(() => expect(view.queryByText('Check change 1')).toBeNull());
  expect(await orderActionStore.list(owner)).toHaveLength(0);
  expect(stored.get(actionId)?.status).toBe('pending');
  expect(requests).toHaveLength(count);
  expect(executes()).toHaveLength(0);
  expect(signEthereumTypedData).not.toHaveBeenCalled();
});

it('recovers a lost response with its original change and separate current order without executing twice', async () => {
  const view = await render(<TradingScreen />, { wrapper });
  await begin(view);
  handler = async (config) => {
    const reply = await ordinary(config);
    if (config.method === 'post') throw new Error('Synthetic lost committed response');
    return reply;
  };
  await fireEvent.press(view.getByText('Sign with biometric'));
  await waitFor(() => expect(view.getByText('Action status unconfirmed')).toBeTruthy());
  const count = requests.length;
  await fireEvent.press(view.getByText('Check change status'));
  await waitFor(() => expect(view.getByText('Original action recovered')).toBeTruthy());
  expect(requests.slice(count).map((request) => request.url)).toEqual([endpoints.ACTION(actionId)]);
  expect(view.getByText('price per share: 12.50 → 14.00')).toBeTruthy();
  expect(view.getByText('Current order status: cancelled')).toBeTruthy();
  expect(executes()).toHaveLength(1);
  expect(await orderActionStore.list(owner)).toHaveLength(0);
});

it('restart recovery bypasses context and forwards the recorded full values with the same ID', async () => {
  context = actionContext(largeQuantity, largeMinimum);
  const first = await render(<TradingScreen />, { wrapper });
  await begin(first);
  await first.unmount();
  const count = requests.length;
  const view = await render(<TradingScreen />, { wrapper });
  await waitFor(() => expect(view.getByText('Check change 1')).toBeTruthy());
  await fireEvent.press(view.getByText('Check change 1'));
  await waitFor(() => expect(view.getByText(`New quantity: ${largeQuantity} shares`)).toBeTruthy());
  expect(requests.slice(count).map((request) => request.url)).toEqual([
    endpoints.ACTION(actionId),
    endpoints.MODIFY_MESSAGE(orderUuid),
  ]);
  expect(JSON.parse(messagePosts().at(-1)!.data).new_quantity).toBe(largeQuantity);
  expect(signEthereumTypedData).not.toHaveBeenCalled();
});

it.each(['cancel', 'modify'] as const)('accepts a validated stored %s refusal', async (purpose) => {
  const view = await render(<TradingScreen />, { wrapper });
  await begin(view, purpose);
  handler = async (config) => {
    const data = actionSnapshot(purpose, 'refused');
    return fail(config, data, data.refusal!.httpStatus);
  };
  await fireEvent.press(view.getByText('Sign with biometric'));
  await waitFor(() =>
    expect(view.getByText(purpose === 'cancel' ? 'Cancellation declined' : 'Change declined')).toBeTruthy(),
  );
  expect(await orderActionStore.list(owner)).toHaveLength(0);
});

it.each(['action_intent_conflict', 'action_context_conflict'])(
  'does not mistake ordinary %s for a terminal refusal',
  async (code) => {
    const view = await render(<TradingScreen />, { wrapper });
    await begin(view);
    handler = async (config) => fail(config, { code, detail: 'Synthetic ordinary conflict' }, 409);
    await fireEvent.press(view.getByText('Sign with biometric'));
    await waitFor(() => expect(view.getByText('Action status unconfirmed')).toBeTruthy());
    expect(await orderActionStore.list(owner)).toHaveLength(1);
    expect(view.queryByText('Change declined')).toBeNull();
  },
);

it.each(['close', 'account', 'session'] as const)(
  'retires a biometric seed read after %s before signing or executing',
  async (retirement) => {
    const view = await render(<TradingScreen />, { wrapper });
    await begin(view);
    const seed = deferred<string>();
    jest.mocked(getSeedPhrase).mockReturnValueOnce(seed.promise);
    await fireEvent.press(view.getByText('Sign with biometric'));
    expect(getSeedPhrase).toHaveBeenCalledTimes(1);
    if (retirement === 'close') await fireEvent.press(view.getByText('Dismiss window'));
    else
      await act(async () => {
        if (retirement === 'account') setAccount(otherAccountUuid);
        else invalidateSessionScope();
      });
    await act(async () => {
      seed.resolve('synthetic-late-seed');
      await seed.promise;
    });
    expect(signEthereumTypedData).not.toHaveBeenCalled();
    expect(executes()).toHaveLength(0);
    expect(await orderActionStore.list(owner)).toHaveLength(1);
  },
);

it('ignores delayed context A after selecting B before either action is issued', async () => {
  const late = deferred<AxiosResponse>();
  handler = (config) => (config.url === endpoints.ACTION_CONTEXT(orderUuid) ? late.promise : ordinary(config));
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(view.getByText('Change synthetic order'));
  await fireEvent.press(view.getByText('Change other order'));
  await waitFor(() => expect(view.getByText('Review change')).toBeTruthy());
  const first = requests.find((request) => request.url === endpoints.ACTION_CONTEXT(orderUuid))!;
  await act(async () => {
    late.resolve(response(first, { ...context, currentValues: { ...context.currentValues, quantity: '999' } }));
    await late.promise;
  });
  expect(view.getByLabelText('New quantity').props.value).toBe('10');
  expect(requests.some((request) => request.url === endpoints.ACTION_CONTEXT(otherOrderUuid))).toBe(true);
  expect(messagePosts()).toHaveLength(0);
  expect(await orderActionStore.list(owner)).toHaveLength(0);
});

it('storage failure prevents first message and retries with the same reserved identity', async () => {
  jest.mocked(AsyncStorage.setItem).mockRejectedValueOnce(new Error('Synthetic storage failure'));
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(view.getByText('Cancel synthetic order'));
  await waitFor(() => expect(view.getByText('Review cancellation')).toBeTruthy());
  await fireEvent.press(view.getByText('Review cancellation'));
  await waitFor(() => expect(view.getByText('Action status unconfirmed')).toBeTruthy());
  expect(messagePosts()).toHaveLength(0);
  expect(Crypto.randomUUID).toHaveBeenCalledTimes(1);
  await fireEvent.press(view.getByText('Check cancellation status'));
  await waitFor(() => expect(view.getByText('Sign with biometric')).toBeTruthy());
  expect(Crypto.randomUUID).toHaveBeenCalledTimes(1);
  expect(JSON.parse(messagePosts()[0]!.data).action_id).toBe(actionId);
});

it('two deliberately separate identical changes retain separate saved identities', async () => {
  const view = await render(<TradingScreen />, { wrapper });
  await begin(view);
  await fireEvent.press(view.getByText('Dismiss window'));
  await begin(view);
  expect(await orderActionStore.list(owner)).toHaveLength(2);
  expect(messagePosts().map((request) => JSON.parse(request.data).action_id)).toEqual([actionId, otherActionId]);
});

it('retains real typed QR encoding and decoding and fences a scan callback from a closed action', async () => {
  wallet.signingPreference = 'hardware';
  context = actionContext(largeQuantity, largeMinimum);
  const view = await render(<TradingScreen />, { wrapper });
  await begin(view);
  await fireEvent.press(view.getByText('Show signing code'));
  const cbor = jest.mocked(QRDisplay).mock.calls.at(-1)![0].data;
  if (typeof cbor !== 'string') throw new Error('Expected encoded CBOR hex.');
  const payload = JSON.parse(EthSignRequest.fromCBOR(Buffer.from(cbor, 'hex')).getSignData().toString());
  expect(payload.message).toMatchObject({
    actionId,
    orderUuid,
    newQuantity: largeQuantity,
    newMinQuantity: largeMinimum,
  });
  await fireEvent.press(view.getByText("I've signed it"));
  const scanner = jest
    .mocked(QRScanner)
    .mock.calls.filter(([props]) => props.visible)
    .at(-1)![0];
  await act(async () => {
    scanner.onClose();
  });
  await fireEvent.press(view.getByText('Dismiss window'));
  await begin(view);
  const signature = new ETHSignature(Buffer.alloc(65, 1)).toUREncoder(400).nextPart();
  await act(async () => {
    scanner.onScan(signature);
  });
  expect(executes()).toHaveLength(0);
  await fireEvent.press(view.getByText('Show signing code'));
  await fireEvent.press(view.getByText("I've signed it"));
  const nextScan = jest
    .mocked(QRScanner)
    .mock.calls.filter(([props]) => props.visible)
    .at(-1)![0].onScan;
  await act(async () => {
    nextScan(signature);
    nextScan(signature);
  });
  await waitFor(() => expect(view.getByText('Action recorded')).toBeTruthy());
  expect(executes()).toHaveLength(1);
  expect(JSON.parse(executes()[0]!.data).action_id).toBe(otherActionId);
  expect(await orderActionStore.list(owner)).toHaveLength(1);
});

it('does not choose a same-address wallet with a different UUID for signing', async () => {
  wallet.uuid = '30000000-0000-4000-8000-000000000009';
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(view.getByText('Cancel synthetic order'));
  await waitFor(() => expect(view.getByText('Review cancellation')).toBeTruthy());
  await fireEvent.press(view.getByText('Review cancellation'));
  await waitFor(() => expect(view.getByText('Show signing code')).toBeTruthy());
  await fireEvent.press(view.getByText('Show signing code'));
  expect(QRDisplay).not.toHaveBeenCalled();
  expect(getSeedPhrase).not.toHaveBeenCalled();
  expect(executes()).toHaveLength(0);
  expect(await orderActionStore.list(owner)).toHaveLength(1);
});

it('keeps an unverified exact wallet eligible to cancel an existing order', async () => {
  wallet.verificationStatus = 'PENDING';
  const view = await render(<TradingScreen />, { wrapper });
  await begin(view, 'cancel');
  await fireEvent.press(view.getByText('Sign with biometric'));
  await waitFor(() => expect(view.getByText('Action recorded')).toBeTruthy());
  expect(executes()).toHaveLength(1);
});

it.each(['executing', 'failed'])(
  'recovers original modification and separately displays the later %s order',
  async (status) => {
    const view = await render(<TradingScreen />, { wrapper });
    await begin(view);
    handler = async (config) => {
      const reply = await ordinary(config);
      if (config.method === 'post') throw new Error('Synthetic lost committed response');
      reply.data.order.status = status;
      return reply;
    };
    await fireEvent.press(view.getByText('Sign with biometric'));
    await waitFor(() => expect(view.getByText('Action status unconfirmed')).toBeTruthy());
    const count = requests.length;
    await fireEvent.press(view.getByText('Check change status'));
    await waitFor(() => expect(view.getByText('Original action recovered')).toBeTruthy());
    expect(view.getByText('price per share: 12.50 → 14.00')).toBeTruthy();
    expect(view.getByText(`Current order status: ${status}`)).toBeTruthy();
    expect(requests.slice(count).map((request) => request.url)).toEqual([endpoints.ACTION(actionId)]);
    expect(executes()).toHaveLength(1);
    expect(await orderActionStore.list(owner)).toHaveLength(0);
  },
);
