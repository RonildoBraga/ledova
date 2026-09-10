// @vitest-environment jsdom

import type { PropsWithChildren, ReactNode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { ApiClientProvider, AUTH_QUERY_KEY, USER_PREFERENCES_QUERY_KEY, TRADING_ENDPOINTS } from '@ledova/shared';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { TradingPage } from './index';
import { deriveAddress, signEthereumTypedData } from '@utils/softwareWallet/localSigner';
import { orderSubmissionStore } from '@services/orderSubmissions';
import {
  accountUuid,
  deferred,
  largeMinQuantity,
  largeQuantity,
  largeSnapshotJson,
  otherAccountUuid,
  owner,
  response,
  secondId,
  snapshot,
  submissionId,
  userUuid,
  wallet,
} from '../../../../packages/shared/tests/fixtures/order-submissions';

vi.mock('@components/Modal', () => ({
  Modal: ({
    isOpen,
    children,
    title,
    onClose,
    onConfirm,
    confirmLabel,
    confirmDisabled,
  }: {
    isOpen: boolean;
    children: ReactNode;
    title: string;
    onClose: () => void;
    onConfirm?: () => void;
    confirmLabel?: string;
    confirmDisabled?: boolean;
  }) =>
    isOpen ? (
      <div role="dialog" aria-label={title}>
        {children}
        <button onClick={onClose}>Dismiss {title}</button>
        {onConfirm && (
          <button disabled={confirmDisabled} onClick={onConfirm}>
            {confirmLabel}
          </button>
        )}
      </div>
    ) : null,
}));
vi.mock('@components/SeedPhraseInput', () => ({
  SeedPhraseInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <input aria-label="Synthetic seed" value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}));
vi.mock('@components/qr', () => ({
  useQRScanner: () => ({ error: null, stopScanner: vi.fn() }),
  QRScannerView: () => null,
}));
vi.mock('@keystonehq/animated-qr', () => ({ AnimatedQRCode: () => null }));
vi.mock('@utils/softwareWallet/localSigner', () => ({ deriveAddress: vi.fn(), signEthereumTypedData: vi.fn() }));
vi.mock('./components/MarketOverview', () => ({ MarketOverview: () => null }));
vi.mock('./components/OrdersPanel', () => ({ OrdersPanel: () => null }));
vi.mock('./components/SwapSigningFlow', () => ({ SwapSigningFlow: () => null }));
vi.mock('./hooks/useTradingEvents', () => ({ useTradingEvents: () => {} }));
vi.mock('./hooks/useAtomicSwaps', () => ({ useSwapOrdersMulti: () => ({ data: [], isLoading: false }) }));
vi.mock('./useTrading', async () => {
  const f = await import('../../../../packages/shared/tests/fixtures/order-submissions');
  const tokens = [{ uuid: f.tokenUuid, name: 'Synthetic', symbol: 'SYN', lastPrice: '12.50' }];
  return {
    useShareTokens: () => ({ data: tokens }),
    useInvestorEligibilityQuery: () => ({ data: { isEligible: true } }),
    useUserTradingWallets: () => ({ wallets: [f.wallet], walletAddresses: [f.wallet.address] }),
    useWalletsWhitelistStatus: () => ({
      isWhitelisted: () => true,
      getStatus: () => ({ status: 'whitelisted' }),
      isLoading: false,
    }),
    useOrderBook: () => ({ data: null }),
    useTrading: () => ({ userOrders: [], getWalletsWithHoldings: () => [] }),
    useOrderCancelMessage: () => ({ mutate: vi.fn() }),
    useCancelOrder: () => ({ mutate: vi.fn() }),
  };
});

const endpoints = TRADING_ENDPOINTS.ORDERS;
let client: QueryClient;
let api = axios.create();
let requests: InternalAxiosRequestConfig[];
let handler: (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>;

function setAccount(account = accountUuid) {
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
function orderPosts() {
  return requests.filter((config) => config.url === endpoints.CREATE);
}
function messagePosts() {
  return requests.filter((config) => config.url === endpoints.CREATE_MESSAGE);
}
async function newOrder() {
  fireEvent.click(screen.getByRole('button', { name: 'New buy order — SYN' }));
  fireEvent.change(screen.getByPlaceholderText('Enter number of shares'), { target: { value: '10' } });
  fireEvent.click(screen.getByRole('button', { name: 'Place Buy Order' }));
  await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
}
function sign() {
  fireEvent.click(screen.getByText('Continue to sign'));
  fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: 'synthetic seed input' } });
  fireEvent.click(screen.getByText('Sign order'));
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  setAccount();
  api = axios.create();
  requests = [];
  handler = async (config) => {
    const id = config.data ? JSON.parse(config.data).submission_id : config.url!.split('/').at(-2);
    return response(
      config,
      snapshot(id, config.url === endpoints.CREATE ? 'created' : 'pending'),
      config.url === endpoints.CREATE ? 201 : 200,
    );
  };
  api.defaults.adapter = async (config) => {
    requests.push(config);
    return handler(config);
  };
  vi.spyOn(crypto, 'randomUUID').mockReturnValueOnce(submissionId).mockReturnValueOnce(secondId);
  vi.mocked(deriveAddress).mockReturnValue(wallet.address);
  vi.mocked(signEthereumTypedData).mockResolvedValue('synthetic-signature');
});
afterEach(() => {
  cleanup();
  client.clear();
  vi.restoreAllMocks();
});

it('uses actual draft/sign callbacks, preserves two equal explicit orders, and latches duplicate presses', async () => {
  const pending = deferred<AxiosResponse>();
  handler = async (config) =>
    config.url === endpoints.CREATE
      ? pending.promise
      : response(config, snapshot(JSON.parse(config.data).submission_id));
  render(<TradingPage />, { wrapper });
  await newOrder();
  expect(await orderSubmissionStore.list(owner)).toHaveLength(1);
  sign();
  await waitFor(() => expect(orderPosts()).toHaveLength(1));
  fireEvent.click(screen.getByText('Close'));
  await newOrder();
  expect(await orderSubmissionStore.list(owner)).toHaveLength(2);
  const signButton = screen.getByText('Continue to sign');
  fireEvent.click(signButton);
  fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: 'synthetic seed input' } });
  const submit = screen.getByText('Sign order');
  act(() => {
    submit.click();
    submit.click();
  });
  await waitFor(() => expect(orderPosts()).toHaveLength(2));
  expect(messagePosts().map((c) => JSON.parse(c.data).submission_id)).toEqual([submissionId, secondId]);
  expect(orderPosts().map((c) => JSON.parse(c.data).submission_id)).toEqual([submissionId, secondId]);
  fireEvent.click(screen.getByText('Close'));
  await act(async () => {
    pending.resolve({ status: 201, data: snapshot(submissionId, 'created') } as AxiosResponse);
  });
  expect(await orderSubmissionStore.list(owner)).toHaveLength(2);
});

it('recovers the current order after a lost response and remount without signing again', async () => {
  handler = async (config) => {
    if (config.url === endpoints.CREATE) throw new Error('Synthetic lost response');
    return response(config, snapshot(submissionId, config.method === 'get' ? 'created' : 'pending'));
  };
  const view = render(<TradingPage />, { wrapper });
  await newOrder();
  sign();
  await waitFor(() => expect(screen.getByText('Order status unconfirmed')).toBeTruthy());
  view.unmount();
  render(<TradingPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Check saved order 1')).toBeTruthy());
  fireEvent.click(screen.getByText('Check saved order 1'));
  await waitFor(() => expect(screen.getByText('Current status: cancelled.')).toBeTruthy());
  expect(messagePosts()).toHaveLength(1);
  expect(orderPosts()).toHaveLength(1);
  expect(signEthereumTypedData).toHaveBeenCalledTimes(1);
  await waitFor(async () => expect(await orderSubmissionStore.list(owner)).toHaveLength(0));
});

it('never manufactures missing terms or a replacement ID when restarted before server admission', async () => {
  await orderSubmissionStore.create(owner, wallet.uuid);
  handler = async (config) => {
    throw new AxiosError('Unavailable', undefined, config, undefined, response(config, { detail: 'Not found.' }, 404));
  };
  render(<TradingPage />, { wrapper });
  await waitFor(() => expect(screen.getByText('Check saved order 1')).toBeTruthy());
  fireEvent.click(screen.getByText('Check saved order 1'));
  await waitFor(() => expect(screen.getByText('Order status unconfirmed')).toBeTruthy());
  expect(screen.queryByText('Continue to sign')).toBeNull();
  expect(requests.map((c) => c.url)).toEqual([endpoints.SUBMISSION(submissionId)]);
  expect(await orderSubmissionStore.list(owner)).toHaveLength(1);
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
});

it.each(['close', 'account'])('does not post or deliver a delayed local signature after %s', async (transition) => {
  const signed = deferred<string>();
  vi.mocked(signEthereumTypedData).mockReturnValue(signed.promise);
  render(<TradingPage />, { wrapper });
  await newOrder();
  sign();
  await waitFor(() => expect(signEthereumTypedData).toHaveBeenCalledTimes(1));
  if (transition === 'close') fireEvent.click(screen.getByText('Close'));
  else
    act(() => {
      setAccount(otherAccountUuid);
    });
  await act(async () => {
    signed.resolve('synthetic-late-signature');
  });
  expect(orderPosts()).toHaveLength(0);
  expect(screen.queryByText('Buy order placed')).toBeNull();
  expect(await orderSubmissionStore.list(owner)).toHaveLength(1);
});

it('does not let a delayed A challenge replace B after explicitly opening another order', async () => {
  const first = deferred<AxiosResponse>();
  handler = async (config) =>
    JSON.parse(config.data).submission_id === submissionId ? first.promise : response(config, snapshot(secondId));
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByText('New buy order — SYN'));
  fireEvent.change(screen.getByPlaceholderText('Enter number of shares'), { target: { value: '10' } });
  fireEvent.click(screen.getByText('Place Buy Order'));
  await waitFor(() => expect(messagePosts()).toHaveLength(1));
  fireEvent.click(screen.getByText('Close'));
  await newOrder();
  await act(async () => {
    first.resolve({ data: snapshot(submissionId) } as AxiosResponse);
  });
  sign();
  await waitFor(() => expect(orderPosts()).toHaveLength(1));
  expect(JSON.parse(orderPosts()[0].data).submission_id).toBe(secondId);
});

it('refuses the first HTTP request if persistent storage fails', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('Storage unavailable');
  });
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByText('New buy order — SYN'));
  fireEvent.change(screen.getByPlaceholderText('Enter number of shares'), { target: { value: '10' } });
  fireEvent.click(screen.getByText('Place Buy Order'));
  await waitFor(() => expect(screen.queryByText('Placing...')).toBeNull());
  expect(messagePosts()).toHaveLength(0);
  await waitFor(() =>
    expect(
      screen.getAllByText('The order could not be saved on this device. No signing request was sent.'),
    ).toHaveLength(2),
  );
  expect(messagePosts()).toHaveLength(0);
  expect(orderPosts()).toHaveLength(0);
  expect(screen.getByRole('dialog', { name: 'Buy SYN' })).toBeTruthy();
});

it('latches duplicate draft callbacks before the first persistence turn', async () => {
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByText('New buy order — SYN'));
  fireEvent.change(screen.getByPlaceholderText('Enter number of shares'), { target: { value: '10' } });
  const submit = screen.getByText('Place Buy Order');
  act(() => {
    submit.click();
    submit.click();
  });
  await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
  expect(messagePosts()).toHaveLength(1);
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
  expect(await orderSubmissionStore.list(owner)).toHaveLength(1);
});

it('displays and retries exact recovered quantities above the safe integer range', async () => {
  await orderSubmissionStore.create(owner, wallet.uuid);
  handler = async (config) => {
    if (config.url === endpoints.CREATE && orderPosts().length === 1) throw new Error('Response lost');
    return response(
      config,
      largeSnapshotJson(config.url === endpoints.CREATE ? 'created' : 'pending', config.method !== 'get'),
      config.url === endpoints.CREATE ? 201 : 200,
    );
  };
  render(<TradingPage />, { wrapper });
  fireEvent.click(await screen.findByText('Check saved order 1'));
  await waitFor(() => expect(screen.getByText(`BUY ${largeQuantity} shares`)).toBeTruthy());
  expect(screen.getByText(`Minimum fill: ${largeMinQuantity} shares`)).toBeTruthy();
  sign();
  await waitFor(() => expect(screen.getByText('Order status unconfirmed')).toBeTruthy());
  expect(await orderSubmissionStore.list(owner)).toHaveLength(1);
  fireEvent.click(screen.getByText('Check order status'));
  await waitFor(() => expect(screen.getByText(`BUY ${largeQuantity} shares`)).toBeTruthy());
  expect(screen.getByText(`Minimum fill: ${largeMinQuantity} shares`)).toBeTruthy();
  sign();
  await waitFor(() => expect(screen.getByText('Order created')).toBeTruthy());
  expect(messagePosts()).toHaveLength(2);
  expect(orderPosts()).toHaveLength(2);
  for (const config of [...messagePosts(), ...orderPosts()])
    expect(JSON.parse(config.data)).toMatchObject({
      submission_id: submissionId,
      quantity: largeQuantity,
      min_quantity: largeMinQuantity,
    });
  expect(signEthereumTypedData).toHaveBeenCalledTimes(2);
  for (const call of vi.mocked(signEthereumTypedData).mock.calls)
    expect(call[4]).toMatchObject({ quantity: largeQuantity, minQuantity: largeMinQuantity });
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
  expect(await orderSubmissionStore.list(owner)).toHaveLength(0);
});
