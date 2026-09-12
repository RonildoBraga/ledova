import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Transaction } from 'ethers';
import { ETHSignature } from '@keystonehq/bc-ur-registry-eth';
import {
  ApiClientProvider,
  AUTH_QUERY_KEY,
  USER_PREFERENCES_QUERY_KEY,
  type SwapOrder,
  type Wallet,
  type SwapSettlementResponse,
} from '@ledova/shared';
import { TradingScreen } from './index';
import { QRScanner } from '../../components/qr';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import * as localSigner from '../../utils/softwareWallet/localSigner';
import {
  settlementApprovalTransaction,
  swapSettlementCrypto,
  swapSettlementStore,
} from '../../services/swapSettlements';
import { invalidateSessionScope } from '../../services/sessionScope';
import { deferred, response, wallet as baseWallet } from '../../../../packages/shared/tests/fixtures/order-submissions';
import {
  settlementFixture as fixture,
  settlementResponse,
  settlementOwner as owner,
  settlementNow,
  settlementApproval,
} from '../../../../packages/shared/tests/fixtures/swap-settlements';

jest.mock('uuid', () => ({ v4: () => '70000000-0000-4000-8000-000000000001' }));
jest.mock('expo-crypto', () => ({ randomUUID: () => '70000000-0000-4000-8000-000000000001' }));
jest.mock('../../services/secureKeyStorage', () => ({ getSeedPhrase: jest.fn() }));
jest.mock('../../components/qr', () => ({ QRDisplay: jest.fn(() => null), QRScanner: jest.fn(() => null) }));
let mockBlur: () => void = () => {};
jest.mock('@react-navigation/native', () => ({
  useFocusEffect: (callback: () => () => void) => {
    const React = jest.requireActual('react');
    React.useEffect(() => {
      mockBlur = callback();
      return mockBlur;
    }, [callback]);
  },
}));
jest.mock('../../components/modal', () => {
  const { View, Text, Pressable } = jest.requireActual('react-native');
  return {
    CustomModal: ({
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
            <Text>Dismiss settlement</Text>
          </Pressable>
          {onConfirm && (
            <Pressable disabled={confirmDisabled} onPress={onConfirm}>
              <Text>{confirmLabel}</Text>
            </Pressable>
          )}
        </View>
      ) : null,
  };
});
let mockWallets: Wallet[];
let mockSwaps: SwapOrder[];
jest.mock('./components/OrdersCard', () => {
  const { Pressable, Text } = jest.requireActual('react-native');
  return {
    OrdersCard: ({ swaps, onSignSwap }: { swaps: SwapOrder[]; onSignSwap: (swap: SwapOrder) => void }) => (
      <>
        {swaps.map((swap, index) => (
          <Pressable key={swap.uuid} onPress={() => onSignSwap(swap)}>
            <Text>Open settlement {index + 1}</Text>
          </Pressable>
        ))}
      </>
    ),
  };
});
jest.mock('./components/MarketList', () => ({ MarketList: () => null }));
jest.mock('./components/OrderDetailModal', () => ({ OrderDetailModal: () => null }));
jest.mock('./components/OrderSigningModal', () => ({ OrderSigningModal: () => null }));
jest.mock('./components/CreateOrderModal', () => ({ CreateOrderModal: () => null }));
jest.mock('./components/OrderActionModal', () => ({ OrderActionModal: () => null }));
jest.mock('./components/BuySellButtons', () => ({ BuySellButtons: () => null }));
jest.mock('./components/SwapSigningModal', () => {
  const { Text } = jest.requireActual('react-native');
  return { SwapSigningModal: () => <Text>Legacy settlement route</Text> };
});
jest.mock('./hooks/useTradingEvents', () => ({ useTradingEvents: () => {} }));
jest.mock('./useAtomicSwaps', () => ({ useSwapOrdersMulti: () => ({ data: mockSwaps, refetch: jest.fn() }) }));
jest.mock('./useTrading', () => ({
  useShareTokens: () => ({
    data: [{ uuid: '70000000-0000-4000-8000-000000000005', symbol: 'SYN' }],
    refetch: jest.fn(),
  }),
  useInvestorEligibilityQuery: () => ({ data: { isEligible: true } }),
  useUserTradingWallets: () => ({
    wallets: mockWallets,
    actionWallets: mockWallets,
    walletAddresses: mockWallets.map((wallet) => wallet.address),
  }),
  useWalletsWhitelistStatus: () => ({}),
  useOrderBook: () => ({ data: null }),
  useAllWalletTokenBalances: () => ({ getWalletsWithHoldings: () => [], refetch: jest.fn() }),
  useAllUserOrders: () => ({ orders: [], refetch: jest.fn() }),
}));

const copy = <T,>(data: T): T => JSON.parse(JSON.stringify(data));
let client: QueryClient;
let api = axios.create();
let requests: InternalAxiosRequestConfig[];
let current: SwapSettlementResponse;
let needsApproval: boolean;
let handler: (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>;
const storageSet = jest.mocked(AsyncStorage.setItem).getMockImplementation()!;
function selectedWallet(role: 'seller' | 'buyer' = 'seller'): Wallet {
  const index = role === 'seller' ? 0 : 1;
  const party = fixture.get_body.swapOrder.settlementContext[role];
  return {
    ...baseWallet,
    uuid: party.walletUuid,
    userAccount: party.ownerAccountUuid,
    address: party.address,
    derivationPath: fixture.paths[index],
    masterFingerprint: '12345678',
    verificationStatus: 'VERIFIED',
    signingPreference: 'software',
  };
}
function account(value = current.ownerAccountUuid) {
  client.setQueryData(AUTH_QUERY_KEY, { data: { valid: true } });
  client.setQueryData(USER_PREFERENCES_QUERY_KEY, {
    data: { userProfile: owner.userUuid, selectedAccount: { uuid: value } },
  });
}
function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <ApiClientProvider client={api}>{children}</ApiClientProvider>
    </QueryClientProvider>
  );
}
function posts() {
  return requests.filter((request) => request.method === 'post');
}
async function ordinary(config: InternalAxiosRequestConfig) {
  if (config.url?.endsWith('/swap/') || config.url?.endsWith('/swap/sign/')) {
    if (config.method === 'post') {
      const body = JSON.parse(config.data);
      if (body.signer_address.toLowerCase() === current.swapOrder.sellerAddress.toLowerCase())
        current.swapOrder.sellerHasSigned = true;
      else current.swapOrder.buyerHasSigned = true;
      current.swapOrder.status =
        current.swapOrder.sellerHasSigned && current.swapOrder.buyerHasSigned
          ? 'ready'
          : current.swapOrder.sellerHasSigned
            ? 'seller_signed'
            : 'buyer_signed';
      current.hasSigned =
        current.userRole === 'seller' ? current.swapOrder.sellerHasSigned : current.swapOrder.buyerHasSigned;
      current.canSign = !current.hasSigned && current.swapOrder.status !== 'ready';
      current.admissionRefusal = current.swapOrder.status === 'ready' ? 'swap_not_signable' : null;
      return response(config, copy(current.swapOrder));
    }
    return response(config, copy(current));
  }
  if (config.url?.endsWith('/swap/approval-status/')) {
    const approval = settlementApproval(current);
    const requiredAmount =
      current.userRole === 'seller' ? current.typedData.message.shareAmount : current.typedData.message.paymentAmount;
    return response(config, {
      ...current,
      tokenAddress: approval.tokenAddress,
      tokenSymbol: approval.tokenSymbol,
      requiredAmount,
      currentAllowance: needsApproval ? '0' : requiredAmount,
      needsApproval,
      spender: approval.spender,
    });
  }
  if (config.url?.endsWith('/swap/approval-data/')) return response(config, settlementApproval(current));
  throw new Error('Unexpected synthetic request');
}
async function open(view: Awaited<ReturnType<typeof render>>) {
  await fireEvent.press(view.getByText('Open settlement 1'));
  await waitFor(() => expect(view.getByText('Check token approval')).toBeTruthy());
  await fireEvent.press(view.getByText('Check token approval'));
  await waitFor(() => expect(view.getByText(needsApproval ? 'Review token approval' : 'Sign settlement')).toBeTruthy());
}
async function showAndScan(view: Awaited<ReturnType<typeof render>>) {
  await fireEvent.press(view.getByText('Sign settlement'));
  await fireEvent.press(view.getByText("I've signed it"));
  const props = jest.mocked(QRScanner).mock.calls.at(-1)![0];
  expect(props.visible).toBe(true);
  return props;
}
const signatureQr = (index = 0) =>
  new ETHSignature(Buffer.from(fixture.signatures[index].slice(2), 'hex')).toUREncoder(1000).nextPart();
beforeEach(async () => {
  jest.spyOn(Date, 'now').mockReturnValue(settlementNow);
  current = settlementResponse();
  needsApproval = false;
  mockWallets = [selectedWallet()];
  mockSwaps = [copy(current.swapOrder)];
  await AsyncStorage.clear();
  jest.mocked(AsyncStorage.setItem).mockImplementation(storageSet);
  client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
      mutations: { retry: false, gcTime: Infinity },
    },
  });
  account();
  requests = [];
  handler = ordinary;
  api = axios.create({
    adapter: async (config) => {
      config.ledovaSubmissionGuard?.();
      requests.push(config);
      return handler(config);
    },
  });
  jest.mocked(getSeedPhrase).mockResolvedValue(fixture.mnemonic);
});
afterEach(async () => {
  await cleanup();
  client.clear();
});

it('reviews exact captured terms and sends one real signature despite duplicate presses', async () => {
  const held = deferred<string | null>();
  jest.mocked(getSeedPhrase).mockReturnValue(held.promise);
  const signer = jest.spyOn(localSigner, 'signEthereumTypedData');
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  expect(view.getByText('Shares: 9007199254740993')).toBeTruthy();
  expect(view.getByText('Payment: 13510798882111489.5 TUSD')).toBeTruthy();
  const button = view.getByText('Sign settlement');
  await act(async () => {
    await fireEvent.press(button);
    await fireEvent.press(button);
  });
  held.resolve(fixture.mnemonic);
  await act(async () => {});
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(signer).toHaveBeenCalledTimes(1);
  expect(JSON.parse(posts()[0].data)).toMatchObject({
    signature: fixture.signatures[0],
    signer_address: fixture.addresses[0],
    swap_uuid: current.swapUuid,
    settlement_digest: current.settlementDigest,
  });
  expect(await swapSettlementStore.list(owner)).toHaveLength(0);
});

it('displays signed payment units at the captured deployment precision when pricing differs', async () => {
  current.swapOrder.settlementContext.paymentAsset.deploymentDecimals = 6;
  mockSwaps = [copy(current.swapOrder)];
  const originalTypedData = copy(current.typedData);
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  expect(view.getByText('Payment: 1351079888211.14895 TUSD')).toBeTruthy();
  expect(view.queryByText('Payment: 13510798882111489.5 TUSD')).toBeNull();
  expect(current.typedData).toEqual(originalTypedData);
  expect(posts()).toHaveLength(0);
});

it.each(['close', 'account', 'wallet', 'device', 'screen', 'unmount', 'session'] as const)(
  'retires a held seed read on %s and never revives after restoration',
  async (change) => {
    const held = deferred<string | null>();
    jest.mocked(getSeedPhrase).mockReturnValue(held.promise);
    const signer = jest.spyOn(localSigner, 'signEthereumTypedData');
    const view = await render(<TradingScreen />, { wrapper });
    await open(view);
    await fireEvent.press(view.getByText('Sign settlement'));
    await waitFor(() => expect(getSeedPhrase).toHaveBeenCalledTimes(1));
    if (change === 'close') await fireEvent.press(view.getByText('Dismiss settlement'));
    if (change === 'account') {
      await act(async () => account('90000000-0000-4000-8000-000000000001'));
      await act(async () => account());
    }
    if (change === 'wallet' || change === 'device') {
      const original = mockWallets;
      mockWallets = change === 'wallet' ? [] : [{ ...mockWallets[0], masterFingerprint: '87654321' }];
      await view.rerender(<TradingScreen />);
      mockWallets = original;
      await view.rerender(<TradingScreen />);
    }
    if (change === 'screen') await act(async () => mockBlur());
    if (change === 'unmount') await view.unmount();
    if (change === 'session') await act(async () => invalidateSessionScope());
    held.resolve(fixture.mnemonic);
    await act(async () => {});
    expect(signer).not.toHaveBeenCalled();
    expect(posts()).toHaveLength(0);
  },
);

it('selects the buyer own order and submits the actual recovered counterparty signer', async () => {
  current = settlementResponse('buyer');
  mockWallets = [selectedWallet('buyer')];
  mockWallets[0].signingPreference = 'hardware';
  mockSwaps = [copy(current.swapOrder)];
  account();
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  expect(requests[0].url).toContain(current.orderUuid);
  const scanner = await showAndScan(view);
  await act(async () => scanner.onScan(signatureQr(0)));
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(JSON.parse(posts()[0].data)).toMatchObject({
    signer_address: fixture.addresses[0],
    wallet_uuid: current.walletUuid,
  });
});

it('rejects late QR A recovery after Back and QR B while accepting fresh B', async () => {
  mockWallets[0].signingPreference = 'hardware';
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  const a = await showAndScan(view);
  const held = deferred<string>();
  jest.spyOn(swapSettlementCrypto, 'recoverSigner').mockImplementationOnce(() => held.promise);
  await act(async () => a.onScan(signatureQr()));
  await act(async () => a.onClose());
  const b = await showAndScan(view);
  held.resolve(fixture.addresses[0]);
  await act(async () => {});
  expect(posts()).toHaveLength(0);
  await act(async () => b.onScan(signatureQr()));
  await waitFor(() => expect(posts()).toHaveLength(1));
});

it('retains a lost signature response across restart and recovers without another signer', async () => {
  handler = async (config) => {
    const result = await ordinary(config);
    if (config.method === 'post') throw new Error('Synthetic lost ACK');
    return result;
  };
  const signer = jest.spyOn(localSigner, 'signEthereumTypedData');
  let view = await render(<TradingScreen />, { wrapper });
  await open(view);
  await fireEvent.press(view.getByText('Sign settlement'));
  await waitFor(() => expect(view.getByText('Check saved settlement 1')).toBeTruthy());
  await view.unmount();
  handler = ordinary;
  view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(await view.findByText('Check saved settlement 1'));
  await waitFor(() => expect(view.getByText('Seller signature: recorded')).toBeTruthy());
  expect(signer).toHaveBeenCalledTimes(1);
  expect(posts()).toHaveLength(1);
  expect(await swapSettlementStore.list(owner)).toHaveLength(0);
});

it('refuses ambiguous persistence before send and retains the written reminder', async () => {
  jest.mocked(AsyncStorage.setItem).mockImplementation(async (key, value) => {
    await storageSet(key, value);
    throw new Error('Synthetic ambiguous storage');
  });
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  await fireEvent.press(view.getByText('Sign settlement'));
  await waitFor(() => expect(view.getByText('Check settlement status')).toBeTruthy());
  expect(posts()).toHaveLength(0);
  expect(await swapSettlementStore.list(owner)).toHaveLength(1);
});

it('keeps multiple original approval hashes during recovery and sufficient allowance', async () => {
  const record = {
    version: 1 as const,
    ...owner,
    orderUuid: current.orderUuid,
    swapUuid: current.swapUuid,
    walletUuid: current.walletUuid,
    settlementDigest: current.settlementDigest,
    kind: 'approval' as const,
  };
  const hashes = ['0x' + 'ab'.repeat(32), '0x' + 'cd'.repeat(32)];
  for (const txHash of hashes) await swapSettlementStore.save({ ...record, txHash });
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(await view.findByText('Check saved settlement 2'));
  await waitFor(() => expect(view.getByText('Check token approval')).toBeTruthy());
  await fireEvent.press(view.getByText('Check token approval'));
  await waitFor(() => expect(view.getByText('Sign settlement')).toBeTruthy());
  for (const hash of hashes) expect(view.getByText(hash)).toBeTruthy();
  expect(await swapSettlementStore.list(owner)).toHaveLength(2);
  expect(posts()).toHaveLength(0);
  expect(view.queryByText('Review token approval')).toBeNull();
});

it('keeps explicit legacy routing separate from malformed V1', async () => {
  mockSwaps = [{ ...current.swapOrder, settlementProtocolVersion: 0, settlementContext: null, settlementDigest: '' }];
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(view.getByText('Open settlement 1'));
  expect(view.getByText('Legacy settlement route')).toBeTruthy();
  expect(requests).toHaveLength(0);
  mockSwaps = [{ ...current.swapOrder, settlementContext: null }];
  await view.rerender(<TradingScreen />);
  await fireEvent.press(view.getByText('Open settlement 1'));
  expect(view.queryByText('Legacy settlement route')).toBeNull();
  expect(requests).toHaveLength(0);
  expect(view.getByRole('alert')).toBeTruthy();
});

it('keeps late context A from replacing B and submits only B identity', async () => {
  const a = copy(current);
  const b = copy(current);
  b.swapUuid = '70000000-0000-4000-8000-000000000077';
  b.swapOrder.uuid = b.swapUuid;
  b.swapOrder.settlementContext.swapUuid = b.swapUuid;
  mockSwaps = [a.swapOrder, b.swapOrder];
  const held = deferred<AxiosResponse>();
  let waiting: InternalAxiosRequestConfig;
  handler = async (config) => {
    if (config.method === 'get' && config.url?.endsWith('/swap/') && config.params.swap_uuid === a.swapUuid) {
      waiting = config;
      return held.promise;
    }
    current = b;
    return ordinary(config);
  };
  const view = await render(<TradingScreen />, { wrapper });
  await fireEvent.press(view.getByText('Open settlement 1'));
  await waitFor(() => expect(requests).toHaveLength(1));
  await fireEvent.press(view.getByText('Open settlement 2'));
  await waitFor(() => expect(view.getByText('Check token approval')).toBeTruthy());
  held.resolve(response(waiting!, a));
  await act(async () => {});
  await fireEvent.press(view.getByText('Check token approval'));
  await fireEvent.press(await view.findByText('Sign settlement'));
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(JSON.parse(posts()[0].data).swap_uuid).toBe(b.swapUuid);
});

it('refuses a signature after its original deadline passes during seed retrieval', async () => {
  const held = deferred<string | null>();
  jest.mocked(getSeedPhrase).mockReturnValue(held.promise);
  const signer = jest.spyOn(localSigner, 'signEthereumTypedData');
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  await fireEvent.press(view.getByText('Sign settlement'));
  jest.spyOn(Date, 'now').mockReturnValue(Date.parse(current.swapOrder.expiresAt) + 1000);
  held.resolve(fixture.mnemonic);
  await act(async () => {});
  expect(signer).not.toHaveBeenCalled();
  expect(posts()).toHaveLength(0);
});

it.each([
  [200, 'software'],
  [503, 'software'],
  [200, 'hardware'],
] as const)('binds the actual %s approval outcome through %s signing', async (status, preference) => {
  needsApproval = true;
  mockWallets[0].signingPreference = preference;
  let originalHash = '';
  handler = async (config) => {
    if (!config.url?.endsWith('/approval-broadcast/')) return ordinary(config);
    const raw = JSON.parse(config.data).signed_transaction;
    originalHash = Transaction.from(raw).hash!;
    const result = {
      ...current,
      txHash: originalHash,
      ...(status === 503
        ? { code: 'swap_approval_unconfirmed', detail: 'The original approval outcome is unconfirmed.' }
        : { blockNumber: 1, gasUsed: 21000 }),
    };
    if (status === 503)
      throw new AxiosError(
        'Synthetic uncertainty',
        undefined,
        config,
        undefined,
        response(config, JSON.stringify(result), status),
      );
    return response(config, result);
  };
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  await fireEvent.press(view.getByText('Review token approval'));
  await fireEvent.press(await view.findByText('Sign token approval'));
  if (preference === 'hardware') {
    await fireEvent.press(view.getByText("I've signed it"));
    const raw = await localSigner.signEthereumTransaction(
      fixture.mnemonic,
      fixture.paths[0],
      settlementApprovalTransaction(settlementApproval(current).transaction),
    );
    const signature = Transaction.from(raw).signature!.serialized;
    const qr = new ETHSignature(Buffer.from(signature.slice(2), 'hex')).toUREncoder(1000).nextPart();
    const scanner = jest.mocked(QRScanner).mock.calls.at(-1)![0];
    await act(async () => scanner.onScan(qr));
  }
  await waitFor(() => expect(posts()).toHaveLength(1));
  await waitFor(() =>
    expect(view.getByText(status === 503 ? originalHash : `Original approval confirmed: ${originalHash}`)).toBeTruthy(),
  );
  const records = await swapSettlementStore.list(owner);
  expect(records).toHaveLength(status === 503 ? 1 : 0);
  if (status === 503) expect(records[0]).toMatchObject({ kind: 'approval', txHash: originalHash });
  needsApproval = false;
  await fireEvent.press(view.getByText('Check token approval'));
  await waitFor(() => expect(view.getByText('Sign settlement')).toBeTruthy());
  expect(posts()).toHaveLength(1);
  expect(await swapSettlementStore.list(owner)).toHaveLength(status === 503 ? 1 : 0);
});

it('reconstructs the reviewed hardware approval and refuses an unrelated scanned signer', async () => {
  needsApproval = true;
  mockWallets[0].signingPreference = 'hardware';
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  await fireEvent.press(view.getByText('Review token approval'));
  await fireEvent.press(await view.findByText('Sign token approval'));
  await fireEvent.press(view.getByText("I've signed it"));
  const scanner = jest.mocked(QRScanner).mock.calls.at(-1)![0];
  await act(async () => scanner.onScan(signatureQr(1)));
  await waitFor(() => expect(view.getByRole('alert')).toBeTruthy());
  expect(posts()).toHaveLength(0);
  expect(await swapSettlementStore.list(owner)).toHaveLength(0);
});

it('keeps either owned unsigned side visible in the actual orders list and displays exact V1 shares', async () => {
  const { OrdersCard } = jest.requireActual<typeof import('./components/OrdersCard')>('./components/OrdersCard');
  const swap = { ...current.swapOrder, sellerHasSigned: true, status: 'seller_signed' as const };
  const props = {
    tokenSymbol: swap.shareTokenSymbol,
    orderBook: null,
    isLoadingOrderBook: false,
    userOrders: [],
    isLoadingUserOrders: false,
    onCancelOrder: jest.fn(),
    onEditOrder: jest.fn(),
    onViewOrder: jest.fn(),
    swaps: [swap],
    isLoadingSwaps: false,
    walletAddresses: fixture.addresses,
    onSignSwap: jest.fn(),
  };
  const view = await render(<OrdersCard {...props} />);
  expect(view.getByText('9007199254740993 shares')).toBeTruthy();
  expect(view.getByText('Buyer')).toBeTruthy();
  await fireEvent.press(view.getByText('Sign'));
  expect(props.onSignSwap).toHaveBeenCalledWith(swap);
  await view.rerender(<OrdersCard {...props} swaps={[{ ...swap, buyerHasSigned: true, status: 'ready' }]} />);
  expect(view.queryByText('Sign')).toBeNull();
});

it('permanently retires on a wallet-cache material change and restoration in one React batch', async () => {
  const held = deferred<string | null>();
  jest.mocked(getSeedPhrase).mockReturnValue(held.promise);
  const signer = jest.spyOn(localSigner, 'signEthereumTypedData');
  const key = ['wallets', current.ownerAccountUuid, 'trading'];
  client.setQueryData(key, { data: { results: copy(mockWallets) } });
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  await fireEvent.press(view.getByText('Sign settlement'));
  await act(async () => {
    client.setQueryData(key, { data: { results: [{ ...mockWallets[0], masterFingerprint: '87654321' }] } });
    client.setQueryData(key, { data: { results: copy(mockWallets) } });
  });
  held.resolve(fixture.mnemonic);
  await act(async () => {});
  expect(signer).not.toHaveBeenCalled();
  expect(posts()).toHaveLength(0);
});

it.each([true, false])('chooses the remaining buyer side with signed or unbound seller (%s)', async (sellerSigned) => {
  current = settlementResponse('buyer');
  current.swapOrder.sellerHasSigned = sellerSigned;
  current.swapOrder.status = sellerSigned ? 'seller_signed' : 'created';
  mockWallets = [selectedWallet(), selectedWallet('buyer')];
  if (!sellerSigned) mockWallets[0].address = '0x' + 'aa'.repeat(20);
  mockSwaps = [copy(current.swapOrder)];
  account();
  const view = await render(<TradingScreen />, { wrapper });
  await open(view);
  expect(view.getByText('Your role: buyer')).toBeTruthy();
  await fireEvent.press(view.getByText('Sign settlement'));
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(posts()[0].url).toContain(current.swapOrder.buyOrderUuid);
  expect(JSON.parse(posts()[0].data).signature).toBe(fixture.signatures[1]);
});

it('keeps an ordinary V0 unsigned seller visible in the actual orders list', async () => {
  const { OrdersCard } = jest.requireActual<typeof import('./components/OrdersCard')>('./components/OrdersCard');
  const swap = {
    ...current.swapOrder,
    settlementProtocolVersion: 0 as const,
    settlementContext: null,
    settlementDigest: '',
    shareAmount: 10,
  };
  const view = await render(
    <OrdersCard
      tokenSymbol={swap.shareTokenSymbol}
      orderBook={null}
      isLoadingOrderBook={false}
      userOrders={[]}
      isLoadingUserOrders={false}
      onCancelOrder={() => {}}
      onEditOrder={() => {}}
      onViewOrder={() => {}}
      swaps={[swap]}
      isLoadingSwaps={false}
      walletAddresses={[swap.sellerAddress]}
      onSignSwap={() => {}}
    />,
  );
  expect(view.getByText('10 shares')).toBeTruthy();
  expect(view.getByText('Seller')).toBeTruthy();
  expect(view.getByText('Sign')).toBeTruthy();
});

it('displays exact V1 shares in the actual list before either party has signed', async () => {
  const { OrdersCard } = jest.requireActual<typeof import('./components/OrdersCard')>('./components/OrdersCard');
  const swap = current.swapOrder;
  const view = await render(
    <OrdersCard
      tokenSymbol={swap.shareTokenSymbol}
      orderBook={null}
      isLoadingOrderBook={false}
      userOrders={[]}
      isLoadingUserOrders={false}
      onCancelOrder={() => {}}
      onEditOrder={() => {}}
      onViewOrder={() => {}}
      swaps={[swap]}
      isLoadingSwaps={false}
      walletAddresses={[swap.sellerAddress]}
      onSignSwap={() => {}}
    />,
  );
  expect(view.getByText('9007199254740993 shares')).toBeTruthy();
  expect(view.getByText('Seller')).toBeTruthy();
});
