// @vitest-environment jsdom

import type { PropsWithChildren, ReactNode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import axios, { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import {
  ApiClientProvider,
  AUTH_QUERY_KEY,
  USER_PREFERENCES_QUERY_KEY,
  TRADING_ENDPOINTS,
  type OrderActionContext,
  type OrderActionSnapshot,
  type TransferOrder,
} from '@ledova/shared';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { TradingPage } from './index';
import { useQRScanner } from '@components/qr';
import { AnimatedQRCode } from '@keystonehq/animated-qr';
import { DataItem, extend, type DataItemMap } from '@keystonehq/bc-ur-registry';
import { UR, UREncoder } from '@ngraveio/bc-ur';
import { deriveAddress, signEthereumTypedData } from '@utils/softwareWallet/localSigner';
import { orderActionStore } from '@services/orderActions';
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

vi.mock('uuid', async (importOriginal) => ({
  ...(await importOriginal<typeof import('uuid')>()),
  v4: () => '70000000-0000-4000-8000-000000000099',
}));

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
  useQRScanner: vi.fn(() => ({ error: null, stopScanner: vi.fn() })),
  QRScannerView: () => null,
}));
vi.mock('@keystonehq/animated-qr', () => ({ AnimatedQRCode: vi.fn(() => null) }));
vi.mock('@utils/softwareWallet/localSigner', () => ({ deriveAddress: vi.fn(), signEthereumTypedData: vi.fn() }));
vi.mock('./components/MarketOverview', () => ({ MarketOverview: () => null }));
vi.mock('./components/OrdersPanel', async () => {
  const f = await import('../../../../packages/shared/tests/fixtures/order-actions');
  return {
    OrdersPanel: ({
      onCancelOrder,
      onEditOrder,
    }: {
      onCancelOrder: (uuid: string) => void;
      onEditOrder: (order: TransferOrder) => void;
    }) => (
      <>
        <button onClick={() => onCancelOrder(f.orderUuid)}>Cancel synthetic order</button>
        <button
          onClick={() =>
            onEditOrder(f.actionSnapshot('modify', 'pending', f.actionContext(f.largeQuantity, f.largeMinimum)).order)
          }
        >
          Change synthetic order
        </button>
        <button onClick={() => onEditOrder({ ...f.actionSnapshot().order, uuid: f.otherOrderUuid })}>
          Change other order
        </button>
      </>
    ),
  };
});
vi.mock('./components/SwapSigningFlow', () => ({ SwapSigningFlow: () => null }));
vi.mock('./hooks/useTradingEvents', () => ({ useTradingEvents: () => {} }));
vi.mock('./hooks/useAtomicSwaps', () => ({ useSwapOrdersMulti: () => ({ data: [], isLoading: false }) }));
vi.mock('./useTrading', async () => {
  const f = await import('../../../../packages/shared/tests/fixtures/order-submissions');
  const tokens = [{ uuid: f.tokenUuid, name: 'Synthetic', symbol: 'SYN', lastPrice: '12.50' }];
  return {
    useShareTokens: () => ({ data: tokens }),
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
    useTrading: () => ({ userOrders: [], getWalletsWithHoldings: () => [] }),
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
function wrapper({ children }: PropsWithChildren) {
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
async function begin(purpose: 'cancel' | 'modify' = 'modify') {
  fireEvent.click(screen.getByText(purpose === 'cancel' ? 'Cancel synthetic order' : 'Change synthetic order'));
  await waitFor(() =>
    expect(screen.getByText(`Review ${purpose === 'cancel' ? 'cancellation' : 'change'}`)).toBeTruthy(),
  );
  if (purpose === 'modify')
    fireEvent.change(screen.getByLabelText('New price per share'), { target: { value: '14.00' } });
  fireEvent.click(screen.getByText(`Review ${purpose === 'cancel' ? 'cancellation' : 'change'}`));
  await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
}
function sign(purpose: 'cancel' | 'modify' = 'modify') {
  fireEvent.click(screen.getByText('Continue to sign'));
  fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: 'synthetic seed input' } });
  fireEvent.click(screen.getByText(`Sign ${purpose === 'cancel' ? 'cancellation' : 'change'}`));
}
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
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
  vi.spyOn(crypto, 'randomUUID').mockReturnValueOnce(actionId).mockReturnValueOnce(otherActionId);
  vi.mocked(deriveAddress).mockReturnValue(wallet.address);
  vi.mocked(signEthereumTypedData).mockResolvedValue('synthetic-signature');
});
afterEach(() => {
  cleanup();
  client.clear();
  vi.restoreAllMocks();
});

it('first price-only modification keeps exact context values despite the rounded numeric order DTO', async () => {
  context = actionContext(largeQuantity, largeMinimum);
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByText('Change synthetic order'));
  await waitFor(() => expect((screen.getByLabelText('New quantity') as HTMLInputElement).value).toBe(largeQuantity));
  expect((screen.getByLabelText('New minimum fill') as HTMLInputElement).value).toBe(largeMinimum);
  expect(await orderActionStore.list(owner)).toHaveLength(0);
  fireEvent.change(screen.getByLabelText('New price per share'), { target: { value: '14.00' } });
  fireEvent.click(screen.getByText('Review change'));
  await waitFor(() => expect(screen.getByText(`New quantity: ${largeQuantity} shares`)).toBeTruthy());
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
  sign();
  await waitFor(() => expect(screen.getByText('Action recorded')).toBeTruthy());
  expect(vi.mocked(signEthereumTypedData).mock.calls[0]![4]).toMatchObject({
    newQuantity: largeQuantity,
    newMinQuantity: largeMinimum,
    newPricePerShare: '14.00',
    actionId,
  });
  expect(executes()).toHaveLength(1);
  expect(await orderActionStore.list(owner)).toHaveLength(0);
});

it('cancels with the scoped action ID and no create submission', async () => {
  render(<TradingPage />, { wrapper });
  await begin('cancel');
  sign('cancel');
  await waitFor(() =>
    expect(screen.getByText('This cancellation changed the order from open to cancelled.')).toBeTruthy(),
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

it('recovers a lost response with its original change and separate current order without executing twice', async () => {
  render(<TradingPage />, { wrapper });
  await begin();
  handler = async (config) => {
    const reply = await ordinary(config);
    if (config.method === 'post') throw new Error('Synthetic lost committed response');
    return reply;
  };
  sign();
  await waitFor(() => expect(screen.getByText('Action status unconfirmed')).toBeTruthy());
  const count = requests.length;
  fireEvent.click(screen.getByText('Check change status'));
  await waitFor(() => expect(screen.getByText('Original action recovered')).toBeTruthy());
  expect(requests.slice(count).map((request) => request.url)).toEqual([endpoints.ACTION(actionId)]);
  expect(screen.getByText('price per share: 12.50 → 14.00')).toBeTruthy();
  expect(screen.getByText('Current order status: cancelled')).toBeTruthy();
  expect(executes()).toHaveLength(1);
  expect(await orderActionStore.list(owner)).toHaveLength(0);
});

it('restart recovery bypasses context and forwards the recorded full values with the same ID', async () => {
  context = actionContext(largeQuantity, largeMinimum);
  const view = render(<TradingPage />, { wrapper });
  await begin();
  view.unmount();
  const count = requests.length;
  render(<TradingPage />, { wrapper });
  fireEvent.click(await screen.findByText('Check change 1'));
  await waitFor(() => expect(screen.getByText(`New quantity: ${largeQuantity} shares`)).toBeTruthy());
  expect(requests.slice(count).map((request) => request.url)).toEqual([
    endpoints.ACTION(actionId),
    endpoints.MODIFY_MESSAGE(orderUuid),
  ]);
  expect(JSON.parse(messagePosts().at(-1)!.data).new_quantity).toBe(largeQuantity);
  expect(signEthereumTypedData).not.toHaveBeenCalled();
});

it.each(['cancel', 'modify'] as const)(
  'accepts a validated stored %s refusal and keeps ordinary conflicts unresolved',
  async (purpose) => {
    render(<TradingPage />, { wrapper });
    await begin(purpose);
    handler = async (config) => {
      const data = actionSnapshot(purpose, 'refused');
      return fail(config, data, data.refusal!.httpStatus);
    };
    sign(purpose);
    await waitFor(() =>
      expect(screen.getByText(purpose === 'cancel' ? 'Cancellation declined' : 'Change declined')).toBeTruthy(),
    );
    expect(await orderActionStore.list(owner)).toHaveLength(0);
  },
);

it.each(['action_intent_conflict', 'action_context_conflict'])(
  'does not mistake ordinary %s for a terminal refusal',
  async (code) => {
    render(<TradingPage />, { wrapper });
    await begin();
    handler = async (config) => fail(config, { code, detail: 'Synthetic ordinary conflict' }, 409);
    sign();
    await waitFor(() => expect(screen.getByText('Action status unconfirmed')).toBeTruthy());
    expect(await orderActionStore.list(owner)).toHaveLength(1);
    expect(screen.queryByText('Change declined')).toBeNull();
  },
);

it.each(['close', 'account'] as const)(
  'retires delayed software signing after %s with no late execute',
  async (retirement) => {
    render(<TradingPage />, { wrapper });
    await begin();
    const signed = deferred<string>();
    vi.mocked(signEthereumTypedData).mockReturnValueOnce(signed.promise);
    sign();
    expect(signEthereumTypedData).toHaveBeenCalledTimes(1);
    if (retirement === 'close') fireEvent.click(screen.getByText('Close'));
    else act(() => setAccount(otherAccountUuid));
    await act(async () => {
      signed.resolve('synthetic-late-signature');
      await signed.promise;
    });
    expect(executes()).toHaveLength(0);
    expect(await orderActionStore.list(owner)).toHaveLength(1);
  },
);

it('ignores delayed context A after selecting B before either action is issued', async () => {
  const late = deferred<AxiosResponse>();
  handler = (config) => (config.url === endpoints.ACTION_CONTEXT(orderUuid) ? late.promise : ordinary(config));
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByText('Change synthetic order'));
  fireEvent.click(screen.getByText('Change other order'));
  await waitFor(() => expect(screen.getByText('Review change')).toBeTruthy());
  const first = requests.find((request) => request.url === endpoints.ACTION_CONTEXT(orderUuid))!;
  await act(async () => {
    late.resolve(response(first, { ...context, currentValues: { ...context.currentValues, quantity: '999' } }));
    await late.promise;
  });
  expect((screen.getByLabelText('New quantity') as HTMLInputElement).value).toBe('10');
  expect(requests.some((request) => request.url === endpoints.ACTION_CONTEXT(otherOrderUuid))).toBe(true);
  expect(messagePosts()).toHaveLength(0);
  expect(await orderActionStore.list(owner)).toHaveLength(0);
});

it('storage failure prevents the first message and retries with the same reserved identity', async () => {
  const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => {
    throw new Error('Synthetic storage failure');
  });
  render(<TradingPage />, { wrapper });
  fireEvent.click(screen.getByText('Cancel synthetic order'));
  fireEvent.click(await screen.findByText('Review cancellation'));
  await waitFor(() => expect(screen.getByText('Action status unconfirmed')).toBeTruthy());
  expect(messagePosts()).toHaveLength(0);
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
  write.mockRestore();
  fireEvent.click(screen.getByText('Check cancellation status'));
  await waitFor(() => expect(screen.getByText('Continue to sign')).toBeTruthy());
  expect(crypto.randomUUID).toHaveBeenCalledTimes(1);
  expect(JSON.parse(messagePosts()[0]!.data).action_id).toBe(actionId);
});

it('two deliberately separate identical changes retain separate saved identities', async () => {
  render(<TradingPage />, { wrapper });
  await begin();
  fireEvent.click(screen.getByText('Close'));
  await begin();
  expect(await orderActionStore.list(owner)).toHaveLength(2);
  expect(messagePosts().map((request) => JSON.parse(request.data).action_id)).toEqual([actionId, otherActionId]);
});

it('does not choose a same-address wallet with a different UUID for signing', async () => {
  wallet.uuid = '30000000-0000-4000-8000-000000000009';
  render(<TradingPage />, { wrapper });
  await begin('cancel');
  expect((screen.getByText('Continue to sign') as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByText('Continue to sign'));
  expect(signEthereumTypedData).not.toHaveBeenCalled();
  expect(executes()).toHaveLength(0);
  expect(await orderActionStore.list(owner)).toHaveLength(1);
});

it('keeps an unverified exact wallet eligible to cancel an existing order', async () => {
  wallet.verificationStatus = 'PENDING';
  render(<TradingPage />, { wrapper });
  await begin('cancel');
  sign('cancel');
  await waitFor(() => expect(screen.getByText('Action recorded')).toBeTruthy());
  expect(executes()).toHaveLength(1);
});

it('retires the real QR scan callback after closing and executes the next action only once', async () => {
  wallet.signingPreference = 'hardware';
  context = actionContext(largeQuantity, largeMinimum);
  render(<TradingPage />, { wrapper });
  await begin();
  fireEvent.click(screen.getByText('Continue to sign'));
  const cbor = vi.mocked(AnimatedQRCode).mock.calls.at(-1)![0].cbor;
  const request = extend.decodeToDataItem(Buffer.from(cbor, 'hex')).getData() as DataItemMap;
  expect(JSON.parse((request[2] as Buffer).toString()).message).toMatchObject({
    actionId,
    orderUuid,
    newQuantity: largeQuantity,
    newMinQuantity: largeMinimum,
  });
  fireEvent.click(screen.getByText("I've signed it"));
  const stale = vi
    .mocked(useQRScanner)
    .mock.calls.filter(([options]) => options.enabled)
    .at(-1)![0].onScanSuccess;
  fireEvent.click(screen.getByText('Close'));
  await begin();
  const ur = new UREncoder(
    new UR(extend.encodeDataItem(new DataItem({ 2: Buffer.alloc(65, 1) })), 'eth-signature'),
    400,
  ).nextPart();
  await act(async () => {
    stale(ur);
  });
  expect(executes()).toHaveLength(0);
  fireEvent.click(screen.getByText('Continue to sign'));
  fireEvent.click(screen.getByText("I've signed it"));
  const current = vi
    .mocked(useQRScanner)
    .mock.calls.filter(([options]) => options.enabled)
    .at(-1)![0].onScanSuccess;
  await act(async () => {
    current(ur);
    current(ur);
  });
  await waitFor(() => expect(screen.getByText('Action recorded')).toBeTruthy());
  expect(executes()).toHaveLength(1);
  expect(JSON.parse(executes()[0]!.data).action_id).toBe(otherActionId);
  expect(await orderActionStore.list(owner)).toHaveLength(1);
});
