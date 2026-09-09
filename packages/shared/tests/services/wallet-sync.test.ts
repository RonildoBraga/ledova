import type { AxiosInstance } from 'axios';
import { syncWallet } from '../../src/services/wallet-verification';

describe('wallet sync outcomes', () => {
  const post = jest.fn();
  const client = { post } as unknown as AxiosInstance;

  beforeEach(() => post.mockReset());

  it('returns the refreshed wallet only when the complete sync succeeded', async () => {
    const response = { data: { success: true, wallet: { uuid: 'wallet' }, syncResult: { status: 'success' } } };
    post.mockResolvedValue(response);
    await expect(syncWallet(client, 'wallet', 'account')).resolves.toBe(response);
    expect(post).toHaveBeenCalledWith('/api/wallets/wallet/sync/', {}, { params: { user_account: 'account' } });
  });

  it.each([
    [false, 'skipped', 'Verify this wallet before syncing it.'],
    [false, 'error', 'Some wallet balances could not be refreshed. Please try again later.'],
    [true, 'skipped', 'Verify this wallet before syncing it.'],
  ])('rejects a refused or incomplete result even from an older server (%s, %s)', async (success, status, error) => {
    post.mockResolvedValue({ data: { success, wallet: { uuid: 'wallet' }, syncResult: { status, error } } });
    await expect(syncWallet(client, 'wallet')).rejects.toMatchObject({ message: error, isUserFriendly: true });
  });

  it.each([false, true])('does not display raw provider errors from an older server (success: %s)', async (success) => {
    post.mockResolvedValue({
      data: {
        success,
        syncResult: { status: 'error', error: 'Provider failed: https://rpc.example/v2/private-api-key?token=secret' },
      },
    });
    await expect(syncWallet(client, 'wallet')).rejects.toMatchObject({
      message: 'Wallet sync could not finish. Please try again later.',
      isUserFriendly: true,
    });
  });

  it('keeps HTTP failures available to the clients error handler', async () => {
    const failure = { response: { status: 503, data: { detail: 'The service is unavailable.' } } };
    post.mockRejectedValue(failure);
    await expect(syncWallet(client, 'wallet')).rejects.toBe(failure);
  });
});
