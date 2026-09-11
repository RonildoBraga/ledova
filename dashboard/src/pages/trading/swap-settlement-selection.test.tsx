// @vitest-environment jsdom

import type { PropsWithChildren, ReactNode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios, { type InternalAxiosRequestConfig } from 'axios';
import {
  ApiClientProvider,
  AUTH_QUERY_KEY,
  USER_PREFERENCES_QUERY_KEY,
  type SwapOrder,
  type SwapSettlementResponse,
  type Wallet,
} from '@ledova/shared';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { swapSettlementStore } from '@services/swapSettlements';
import * as localSigner from '@utils/softwareWallet/localSigner';
import { TradingPage } from './index';
import fixture from '../../../../packages/shared/tests/fixtures/swap-settlement-api.json';
import { deferred, response, userUuid } from '../../../../packages/shared/tests/fixtures/order-submissions';

const state = vi.hoisted(() => ({ wallets: [] as Wallet[], swaps: [] as SwapOrder[] }));
vi.mock('@components/Modal', () => ({
  Modal: ({ isOpen, children }: { isOpen: boolean; children: ReactNode }) => (isOpen ? <div>{children}</div> : null),
}));
vi.mock('@components/SeedPhraseInput', () => ({
  SeedPhraseInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <input aria-label="Synthetic seed" value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}));
vi.mock('@components/qr', () => ({
  useQRScanner: () => ({ error: null, stopScanner: () => {} }),
  QRScannerView: () => null,
}));
vi.mock('@keystonehq/animated-qr', () => ({ AnimatedQRCode: () => null }));
vi.mock('./components/MarketOverview', () => ({ MarketOverview: () => null }));
vi.mock('./components/PlaceOrderPanel', () => ({ PlaceOrderPanel: () => null }));
vi.mock('./components/OrderSigningFlow', () => ({ OrderSigningFlow: () => null }));
vi.mock('./components/SwapSigningFlow', () => ({
  SwapSigningFlow: ({ orderUuid }: { orderUuid: string }) => <p>Legacy order: {orderUuid}</p>,
}));
vi.mock('./hooks/useTradingEvents', () => ({ useTradingEvents: () => {} }));
vi.mock('./hooks/useAtomicSwaps', () => ({ useSwapOrdersMulti: () => ({ data: state.swaps, isLoading: false }) }));
vi.mock('./useTrading', () => ({
  useShareTokens: () => ({
    data: [{ uuid: '30ca2374-1201-459b-93b0-6eb8c1a90492', name: 'Synthetic', symbol: 'DEP' }],
    isLoading: false,
  }),
  useInvestorEligibilityQuery: () => ({ data: { isEligible: true } }),
  useUserTradingWallets: () => ({
    wallets: state.wallets,
    actionWallets: state.wallets,
    walletAddresses: state.wallets.map((wallet) => wallet.address),
  }),
  useWalletsWhitelistStatus: () => ({
    isWhitelisted: () => true,
    getStatus: () => ({ status: 'whitelisted' }),
    isLoading: false,
  }),
  useOrderBook: () => ({ data: null, isLoading: false }),
  useTrading: () => ({ userOrders: [], isLoadingUserOrders: false, getWalletsWithHoldings: () => [] }),
}));

const captured = fixture.get_body as SwapSettlementResponse;
const owner = { userUuid, ownerAccountUuid: captured.ownerAccountUuid };
let client: QueryClient;
let requests: InternalAxiosRequestConfig[];
let api = axios.create();

function walletFor(role: 'seller' | 'buyer'): Wallet {
  const party = captured.swapOrder.settlementContext[role];
  return {
    uuid: party.walletUuid,
    userAccount: party.ownerAccountUuid,
    address: party.address,
    chain: 'base',
    verificationStatus: 'VERIFIED',
    signingPreference: 'software',
    derivationPath: fixture.paths[role === 'seller' ? 0 : 1]!,
    masterFingerprint: '12345678',
    createdAt: captured.swapOrder.createdAt,
    updatedAt: captured.swapOrder.createdAt,
    nativeBalance: '0',
    nativeMarketValue: '0',
    marketValue: '0',
  };
}
function setAccount(account = owner.ownerAccountUuid) {
  client.setQueryData(AUTH_QUERY_KEY, { data: { valid: true } });
  client.setQueryData(USER_PREFERENCES_QUERY_KEY, {
    data: { userProfile: userUuid, selectedAccount: { uuid: account } },
  });
}
function wrapper({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={client}>
      <ApiClientProvider client={api}>{children}</ApiClientProvider>
    </QueryClientProvider>
  );
}
function swapRequests() {
  return requests.filter((request) => request.url?.includes('/swap/'));
}

beforeEach(() => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse(captured.swapOrder.createdAt) + 1000);
  localStorage.clear();
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime: Infinity } } });
  setAccount();
  state.wallets = [walletFor('buyer')];
  state.swaps = [structuredClone(captured.swapOrder)];
  requests = [];
  api = axios.create();
  api.defaults.adapter = async (config) => {
    config.ledovaSubmissionGuard?.();
    requests.push(config);
    if (!config.url?.includes('/swap/'))
      return response(config, client.getQueryData<{ data: unknown }>(USER_PREFERENCES_QUERY_KEY)!.data);
    const userRole =
      config.params?.wallet_uuid === captured.swapOrder.settlementContext.seller.walletUuid ? 'seller' : 'buyer';
    const party = captured.swapOrder.settlementContext[userRole];
    const swapOrder = state.swaps.find((swap) => swap.uuid === config.params?.swap_uuid) ?? captured.swapOrder;
    const hasSigned = userRole === 'seller' ? swapOrder.sellerHasSigned : swapOrder.buyerHasSigned;
    const body = {
      ...captured,
      swapOrder,
      userRole,
      orderUuid: party.orderUuid,
      walletUuid: party.walletUuid,
      hasSigned,
      canSign: !hasSigned,
    };
    if (config.method === 'post') {
      const order = { ...swapOrder, buyerHasSigned: true, status: 'buyer_signed' as const };
      state.swaps = state.swaps.map((candidate) => (candidate.uuid === order.uuid ? order : candidate));
      return response(config, order);
    }
    if (config.url.endsWith('/approval-status/'))
      return response(config, {
        ...body,
        tokenAddress: captured.typedData.message.paymentToken,
        tokenSymbol: 'TUSD',
        requiredAmount: captured.typedData.message.paymentAmount,
        currentAllowance: ((1n << 256n) - 1n).toString(),
        needsApproval: false,
        spender: captured.typedData.domain.verifyingContract,
      });
    return response(config, body);
  };
});
afterEach(async () => {
  await cleanup();
  client.clear();
  vi.restoreAllMocks();
});

it('opens the buyer own order and shows exact captured quantities in the real order list', async () => {
  render(<TradingPage />, { wrapper });
  expect(screen.getByText('9007199254740993 DEP · 13510798882111489.50 TUSD')).toBeTruthy();
  fireEvent.click(screen.getByTitle('Sign swap'));
  await waitFor(() => expect(screen.getByText('You are the buyer.')).toBeTruthy());
  expect(swapRequests()).toHaveLength(1);
  expect(swapRequests()[0]!.url).toContain(`/orders/${captured.swapOrder.buyOrderUuid}/swap/`);
  expect(swapRequests()[0]!.params).toMatchObject({
    wallet_uuid: captured.swapOrder.settlementContext.buyer.walletUuid,
    settlement_digest: captured.settlementDigest,
    swap_uuid: captured.swapUuid,
  });
  expect(screen.queryByText(/Legacy order/)).toBeNull();
});

it('keeps the unsigned buyer side available when both wallets are owned and the seller has already signed', async () => {
  state.wallets = [walletFor('seller'), walletFor('buyer')];
  state.swaps = [{ ...captured.swapOrder, sellerHasSigned: true, status: 'seller_signed' }];
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByTitle('Sign swap'));
  await waitFor(() => expect(screen.getByText('You are the buyer.')).toBeTruthy());
  expect(swapRequests()[0]!.url).toContain(`/orders/${captured.swapOrder.buyOrderUuid}/swap/`);
});

it.each([null, {}])('refuses malformed version1 context %j without opening a legacy signer', async (context) => {
  state.swaps = [{ ...captured.swapOrder, settlementContext: context as SwapOrder['settlementContext'] }];
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByTitle('Sign swap'));
  await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
  expect(swapRequests()).toEqual([]);
  expect(screen.queryByText(/Legacy order/)).toBeNull();
});

it('retains the explicit version0 wrapper with the buyer own order', () => {
  state.swaps = [
    { ...captured.swapOrder, settlementProtocolVersion: 0, settlementContext: null, settlementDigest: '' },
  ];
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByTitle('Sign swap'));
  expect(screen.getByText(`Legacy order: ${captured.swapOrder.buyOrderUuid}`)).toBeTruthy();
  expect(swapRequests()).toEqual([]);
});

it('lists multiple scoped reminders and recovers the exact selected identity without any submission', async () => {
  const signature = {
    version: 1 as const,
    ...owner,
    orderUuid: captured.swapOrder.settlementContext.buyer.orderUuid,
    walletUuid: captured.swapOrder.settlementContext.buyer.walletUuid,
    swapUuid: captured.swapUuid,
    settlementDigest: captured.settlementDigest,
    kind: 'signature' as const,
    signerAddress: captured.typedData.message.buyer.toLowerCase(),
  };
  const approval = { ...signature, kind: 'approval' as const, txHash: `0x${'ab'.repeat(32)}` };
  const { signerAddress: removed, ...savedApproval } = approval;
  expect(removed).toBe(signature.signerAddress);
  await swapSettlementStore.save(signature);
  await swapSettlementStore.save(savedApproval);
  await swapSettlementStore.save({ ...signature, userUuid: '10000000-0000-4000-8000-000000000099' });
  const records = await swapSettlementStore.list(owner);
  render(<TradingPage />, { wrapper });
  await waitFor(() =>
    expect(screen.getAllByRole('button', { name: /Check saved (trade signature|approval)/ })).toHaveLength(2),
  );
  for (const [index, record] of records.entries()) {
    fireEvent.click(
      screen.getByText(`Check saved ${record.kind === 'approval' ? 'approval' : 'trade signature'} ${index + 1}`),
    );
    await waitFor(() => expect(swapRequests()).toHaveLength(index + 1));
    expect(swapRequests()[index]!.params).toMatchObject({
      swap_uuid: record.swapUuid,
      wallet_uuid: record.walletUuid,
      owner_account_uuid: record.ownerAccountUuid,
      settlement_digest: record.settlementDigest,
    });
    expect(swapRequests()[index]!.url).toContain(`/orders/${record.orderUuid}/swap/`);
  }
  expect(await swapSettlementStore.list(owner)).toHaveLength(2);
  expect(requests.filter((request) => request.method === 'post')).toEqual([]);
});

it.each(['wallet', 'account'] as const)(
  'a temporary %s change retires the mounted signer even when restored before it finishes',
  async (change) => {
    const signed = deferred<string>();
    const signer = vi.spyOn(localSigner, 'signEthereumTypedData').mockReturnValue(signed.promise);
    const view = render(<TradingPage />, { wrapper });
    fireEvent.click(screen.getByTitle('Sign swap'));
    await waitFor(() => expect(screen.getByText('You are the buyer.')).toBeTruthy());
    fireEvent.click(screen.getByText('Check token approval'));
    await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
    fireEvent.click(screen.getByText('Continue to sign'));
    fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: fixture.mnemonic } });
    fireEvent.click(screen.getByText('Sign trade'));
    await waitFor(() => expect(signer).toHaveBeenCalledOnce());
    if (change === 'wallet') {
      state.wallets = [{ ...state.wallets[0]!, masterFingerprint: '87654321' }];
      view.rerender(<TradingPage />);
      state.wallets = [walletFor('buyer')];
      view.rerender(<TradingPage />);
    } else {
      act(() => setAccount('20000000-0000-4000-8000-000000000099'));
      act(() => setAccount());
    }
    await act(async () => {
      signed.resolve(fixture.signatures[1]!);
      await signed.promise;
    });
    expect(requests.filter((request) => request.method === 'post')).toEqual([]);
    expect(await swapSettlementStore.list(owner)).toEqual([]);
    expect(screen.queryByText('You are the buyer.')).toBeNull();
  },
);

it('latches a wallet cache change and restoration within one React batch before a signer finishes', async () => {
  const key = ['wallets', owner.ownerAccountUuid, 'trading'];
  const original = { data: { results: state.wallets } };
  client.setQueryData(key, original);
  const signed = deferred<string>();
  const signer = vi.spyOn(localSigner, 'signEthereumTypedData').mockReturnValue(signed.promise);
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByTitle('Sign swap'));
  await waitFor(() => expect(screen.getByText('You are the buyer.')).toBeTruthy());
  fireEvent.click(screen.getByText('Check token approval'));
  await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
  fireEvent.click(screen.getByText('Continue to sign'));
  fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: fixture.mnemonic } });
  fireEvent.click(screen.getByText('Sign trade'));
  await waitFor(() => expect(signer).toHaveBeenCalledOnce());
  act(() => {
    client.setQueryData(key, { data: { results: [{ ...state.wallets[0]!, masterFingerprint: '87654321' }] } });
    client.setQueryData(key, original);
  });
  await act(async () => {
    signed.resolve(fixture.signatures[1]!);
    await signed.promise;
  });
  expect(requests.filter((request) => request.method === 'post')).toEqual([]);
  expect(screen.queryByText('You are the buyer.')).toBeNull();
});

it('keeps a reviewed signer current through balance-only and unrelated-account cache changes', async () => {
  const key = ['wallets', owner.ownerAccountUuid, 'trading'];
  client.setQueryData(key, { data: { results: state.wallets } });
  const signed = deferred<string>();
  const signer = vi.spyOn(localSigner, 'signEthereumTypedData').mockReturnValue(signed.promise);
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByTitle('Sign swap'));
  await waitFor(() => expect(screen.getByText('You are the buyer.')).toBeTruthy());
  fireEvent.click(screen.getByText('Check token approval'));
  await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
  fireEvent.click(screen.getByText('Continue to sign'));
  fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: fixture.mnemonic } });
  fireEvent.click(screen.getByText('Sign trade'));
  await waitFor(() => expect(signer).toHaveBeenCalledOnce());
  act(() => {
    client.setQueryData(key, { data: { results: [{ ...state.wallets[0]!, nativeBalance: '5' }] } });
    client.setQueryData(['wallets', '20000000-0000-4000-8000-000000000099', 'trading'], { data: { results: [] } });
  });
  await act(async () => {
    signed.resolve(fixture.signatures[1]!);
    await signed.promise;
  });
  await waitFor(() => expect(screen.getByText('Your signature is recorded. Trade status: buyer_signed.')).toBeTruthy());
  expect(requests.filter((request) => request.method === 'post')).toHaveLength(1);
  expect(await swapSettlementStore.list(owner)).toEqual([]);
});
