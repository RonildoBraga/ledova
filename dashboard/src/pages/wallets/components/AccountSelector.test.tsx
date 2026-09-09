// @vitest-environment jsdom

import { cleanup, fireEvent, render, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { HardwareWalletImport } from '@ledova/shared';

const api = vi.hoisted(() => ({ post: vi.fn() }));
const qr = vi.hoisted(() => ({ decode: vi.fn() }));
vi.mock('@services/apiClient', () => ({ default: api }));
vi.mock('@utils/keystone/bcurDecoder', () => ({ extractFromKeystoneQR: qr.decode }));

import { AccountSelector } from './AddWalletModal';

const address = '0x' + 'a'.repeat(40);
const data: HardwareWalletImport = {
  addresses: [{ address, networkType: 'ETH', addressIndex: 0, derivationPath: "m/44'/60'/0'/0/0" }],
  masterFingerprint: 'fingerprint',
  parentKeys: [{ parentPublicKey: 'public', parentChainCode: 'chain', parentDerivationPath: "m/44'/60'/0'/0" }],
};

beforeEach(() => {
  api.post.mockReset();
  qr.decode.mockReturnValue(data);
});
afterEach(cleanup);

it('queries and imports the selected Base network', async () => {
  api.post.mockImplementation(async (_url, body) => ({
    data: {
      userAccount: body.userAccount,
      chain: body.chain,
      balances: { [address]: body.chain === 'base' ? '2' : '5' },
    },
  }));
  const selected = vi.fn();
  const view = render(
    <AccountSelector
      urString="synthetic-qr"
      userAccountUuid="account"
      onSelectAccounts={selected}
      onCancel={vi.fn()}
      isLoading={false}
    />,
  );
  await view.findByText('5 ETH');
  fireEvent.change(view.getByLabelText('Import EVM network'), { target: { value: 'BASE' } });
  await view.findByText('2 ETH');
  expect(api.post).toHaveBeenLastCalledWith('/api/wallets/batch-check-balances/', {
    userAccount: 'account',
    chain: 'base',
    addresses: [address],
  });
  fireEvent.click(view.getByRole('button', { name: 'Import 1 Wallet' }));
  expect(selected).toHaveBeenCalledWith([{ ...data.addresses[0], networkType: 'BASE' }], {
    ...data,
    addresses: [{ ...data.addresses[0], networkType: 'BASE' }],
  });
});

it('does not display a zero when the provider fails', async () => {
  api.post.mockRejectedValue(new Error('offline'));
  const view = render(
    <AccountSelector
      urString="synthetic-qr"
      userAccountUuid="account"
      onSelectAccounts={vi.fn()}
      onCancel={vi.fn()}
      isLoading={false}
    />,
  );
  await view.findByText('Unavailable');
  expect(view.queryByText('0 ETH')).toBeNull();
});

it('ignores an earlier account response after the selected account changes', async () => {
  let finish!: (response: unknown) => void;
  api.post.mockImplementation(async (_url, body) =>
    body.userAccount === 'old'
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : { data: { userAccount: 'current', chain: 'ethereum', balances: { [address]: '7' } } },
  );
  const props = { urString: 'synthetic-qr', onSelectAccounts: vi.fn(), onCancel: vi.fn(), isLoading: false };
  const view = render(<AccountSelector {...props} userAccountUuid="old" />);
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  view.rerender(<AccountSelector {...props} userAccountUuid="current" />);
  await view.findByText('7 ETH');
  await act(async () => finish({ data: { userAccount: 'old', chain: 'ethereum', balances: { [address]: '99' } } }));
  expect(view.queryByText('99 ETH')).toBeNull();
  expect(view.getByText('7 ETH')).toBeTruthy();
});

it('requires an account before querying or importing', async () => {
  const selected = vi.fn();
  const view = render(
    <AccountSelector
      urString="synthetic-qr"
      userAccountUuid={undefined}
      onSelectAccounts={selected}
      onCancel={vi.fn()}
      isLoading={false}
    />,
  );
  await view.findByText('Unavailable');
  expect(api.post).not.toHaveBeenCalled();
  fireEvent.click(view.getByRole('button', { name: 'Import 1 Wallet' }));
  expect(selected).not.toHaveBeenCalled();
});
