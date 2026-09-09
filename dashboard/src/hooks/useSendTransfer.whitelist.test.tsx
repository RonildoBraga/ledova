// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import apiClient from '@services/apiClient';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Wallet } from '@ledova/shared';

const whitelisted = `0x${'1'.repeat(40)}`;
const notWhitelisted = `0x${'2'.repeat(40)}`;

const wallet = {
  uuid: 'wallet-1',
  address: whitelisted,
  chain: 'base',
  nativeBalance: '1',
  nativeMarketValue: '1',
} as unknown as Wallet;

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
        walletUuid: wallet.uuid,
        chain: wallet.chain,
        quantity: '10000',
        marketValue: '10000',
        assetSymbol: 'QAT',
        assetName: 'QA Token',
        asset: {
          isActive: true,
          assetType: 'tokenized_security',
          chainDeployments: [{ chain: 'base', contractAddress: `0x${'3'.repeat(40)}`, decimals: 0, isActive: true }],
        },
      },
    ],
  }),
);

vi.mock('@services/apiClient', () => ({ default: { get: vi.fn(async () => ({ data: { valid: false } })) } }));

vi.mock('@ledova/shared', async () => {
  const actual = await vi.importActual<typeof import('@ledova/shared')>('@ledova/shared');
  return { ...actual, getWhitelistStatus, getWalletHoldings };
});

vi.mock('./useSelectedPortfolio', () => ({
  useSelectedPortfolio: () => ({ selectedAccount: { uuid: 'account-1' } }),
}));

vi.mock('@pages/wallets/components/WalletSelectionModal', () => ({
  WalletSelectionModal: ({ isOpen, onSelectWallet }: { isOpen: boolean; onSelectWallet: (w: Wallet) => void }) =>
    isOpen ? (
      <button type="button" onClick={() => onSelectWallet(wallet)}>
        pick the wallet
      </button>
    ) : null,
}));

vi.mock('@pages/wallets/components/TransferSigningFlow', () => ({
  TransferSigningFlow: () => null,
}));

const { ApiClientProvider } = await import('@ledova/shared');

const { SendTransferProvider, useSendTransfer } = await import('./useSendTransfer');

function Opener() {
  const { openSendTransfer } = useSendTransfer();
  return (
    <button type="button" onClick={openSendTransfer}>
      open send
    </button>
  );
}

function renderProvider() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ApiClientProvider client={apiClient}>
        <SendTransferProvider>
          <Opener />
        </SendTransferProvider>
      </ApiClientProvider>
    </QueryClientProvider>,
  );
}

describe('the real Send flow, mounted as the app mounts it', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('carries the selected asset into the hook, so the recipient is actually checked', async () => {
    renderProvider();

    fireEvent.click(screen.getByRole('button', { name: /open send/i }));
    fireEvent.click(await screen.findByRole('button', { name: /pick the wallet/i }));
    fireEvent.click(await screen.findByText('QAT'));
    fireEvent.change(screen.getByPlaceholderText('0x...'), { target: { value: notWhitelisted } });

    await waitFor(() => expect(getWhitelistStatus).toHaveBeenCalledWith(expect.anything(), notWhitelisted));
    await waitFor(() => expect(screen.getByText(/Recipient is not whitelisted/i)).toBeDefined());
    expect(screen.getByRole('button', { name: /continue/i }).hasAttribute('disabled')).toBe(true);
  });
});
