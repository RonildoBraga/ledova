import { act, renderHook, waitFor } from '@testing-library/react-native';
import { importAddressKey } from '@ledova/shared';
import type { DerivedAddress } from '@ledova/shared';
import { apiClient } from '../services/apiClient';
import { useFetchBalances } from './useFetchBalances';

jest.mock('../services/apiClient', () => ({ apiClient: { post: jest.fn() } }));

const post = apiClient.post as jest.Mock;
const address: DerivedAddress = {
  address: '0x' + 'a'.repeat(40),
  networkType: 'BASE',
  addressIndex: 0,
  derivationPath: "m/44'/60'/0'/0/0",
};

beforeEach(() => post.mockReset());

it('keeps a failed mobile preview unavailable', async () => {
  post.mockRejectedValue(new Error('offline'));
  const { result } = await renderHook(() => useFetchBalances('account'));
  await act(async () => {
    await result.current!.fetchBalances([address]);
  });
  expect(result.current!.balances.get(importAddressKey(address))).toBe('Unavailable');
  expect(result.current!.isLoadingBalances).toBe(false);
});

it('does not reuse a pending response from a previous account', async () => {
  let finish!: (response: unknown) => void;
  post.mockImplementation(async (_url, body) =>
    body.userAccount === 'old'
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : { data: { userAccount: 'current', chain: 'base', balances: { [address.address]: '7' } } },
  );
  const { result, rerender } = await renderHook(({ account }: { account: string }) => useFetchBalances(account), {
    initialProps: { account: 'old' },
  });
  let pending: Promise<void> | undefined;
  await act(async () => {
    pending = result.current!.fetchBalances([address]);
  });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await rerender({ account: 'current' });
  expect(result.current!.balances.size).toBe(0);
  await act(async () => {
    await result.current!.fetchBalances([address]);
  });
  expect(result.current!.balances.get(importAddressKey(address))).toBe('7 ETH');
  await act(async () => {
    finish({ data: { userAccount: 'old', chain: 'base', balances: { [address.address]: '99' } } });
    await pending;
  });
  expect(result.current!.balances.get(importAddressKey(address))).toBe('7 ETH');
});
