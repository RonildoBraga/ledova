// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Wallet } from '@ledova/shared';

const whitelisted = `0x${'1'.repeat(40)}`;
const notWhitelisted = `0x${'2'.repeat(40)}`;

const getWhitelistStatus = vi.fn((_client: unknown, address: string) =>
  Promise.resolve({
    data: {
      address,
      isWhitelisted: address === whitelisted,
      canReceive: address === whitelisted,
      status: address === whitelisted ? 'whitelisted' : 'not_whitelisted',
    },
  }),
);

const getWalletHoldings = vi.fn(() =>
  Promise.resolve({
    data: [
      {
        uuid: 'holding-1',
        quantity: '10000',
        marketValue: '10000',
        assetSymbol: 'QAT',
        assetName: 'QA Token',
        asset: { contractAddress: `0x${'3'.repeat(40)}`, assetType: 'tokenized_security', decimals: 0 },
      },
    ],
  }),
);

vi.mock('@services/apiClient', () => ({ default: {} }));

vi.mock('@ledova/shared', async () => {
  const actual = await vi.importActual<typeof import('@ledova/shared')>('@ledova/shared');
  return { ...actual, getWhitelistStatus, getWalletHoldings };
});

const { useTransferFlow } = await import('../hooks/useTransferFlow');
const { SendFormModal } = await import('./SendFormModal');

const wallet = {
  uuid: 'wallet-1',
  address: whitelisted,
  chain: 'base',
  nativeBalance: '1',
  nativeMarketValue: '1',
} as unknown as Wallet;

function Harness({ from = wallet }: { from?: Wallet }) {
  const flow = useTransferFlow(from);
  return (
    <SendFormModal
      isOpen
      onClose={() => {}}
      wallet={from}
      assets={flow.assets}
      isLoadingAssets={flow.isLoadingAssets}
      hasShareTokens={flow.hasShareTokens}
      isSenderWhitelisted={flow.isSenderWhitelisted}
      isRecipientWhitelisted={flow.isRecipientWhitelisted}
      isCheckingRecipientWhitelist={flow.isCheckingRecipientWhitelist}
      senderWhitelistStatus={flow.senderWhitelistStatus}
      recipientWhitelistStatus={flow.recipientWhitelistStatus}
      onBack={() => {}}
      onTransfer={flow.handleCombinedTransfer}
      onAddressChange={flow.setToAddress}
      onAssetChange={flow.setSelectedAsset}
    />
  );
}

function renderFlow(from?: Wallet) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness from={from} />
    </QueryClientProvider>,
  );
}

const unwhitelistedSender = { ...wallet, uuid: 'wallet-2', address: notWhitelisted } as unknown as Wallet;

async function chooseTheShareTokenAndType(address: string) {
  const token = await screen.findByText('QAT');
  fireEvent.click(token);
  const field = screen.getByPlaceholderText('0x...');
  fireEvent.change(field, { target: { value: address } });
}

describe('the Send form and the recipient allowlist', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('refuses an unwhitelisted recipient and keeps Continue disabled', async () => {
    renderFlow();

    await chooseTheShareTokenAndType(notWhitelisted);

    await waitFor(() => expect(screen.getByText(/Recipient is not whitelisted/i)).toBeDefined());
    expect(screen.queryByText(/^Recipient is whitelisted$/i)).toBeNull();
    expect(screen.getByRole('button', { name: /continue/i }).hasAttribute('disabled')).toBe(true);
  });

  it('asks the API about the address in the field, not about the sender', async () => {
    renderFlow();

    await chooseTheShareTokenAndType(notWhitelisted);

    await waitFor(() => expect(getWhitelistStatus).toHaveBeenCalledWith(expect.anything(), notWhitelisted));
  });

  it('refuses an unwhitelisted sender, which read the same way and was never reached either', async () => {
    renderFlow(unwhitelistedSender);

    await chooseTheShareTokenAndType(whitelisted);

    await waitFor(() => expect(screen.getByText(/Your wallet is not whitelisted/i)).toBeDefined());
    expect(screen.getByRole('button', { name: /continue/i }).hasAttribute('disabled')).toBe(true);
  });

  it('accepts a whitelisted recipient', async () => {
    renderFlow();

    await chooseTheShareTokenAndType(whitelisted);

    await waitFor(() => expect(screen.getByText(/^Recipient is whitelisted$/i)).toBeDefined());
  });
});
