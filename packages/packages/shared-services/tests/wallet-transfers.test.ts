import type { AxiosInstance } from 'axios';
import { broadcastTransfer, prepareBitcoinTransfer, prepareTransfer } from '../src/wallet-transfers';

describe('wallet transfer services', () => {
  const post = jest.fn();
  const apiClient = { post } as unknown as AxiosInstance;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('posts an EVM prepare request to the wallet prepare endpoint', () => {
    const data = { toAddress: '0x' + 'a'.repeat(40), amountEth: '0.5' };

    prepareTransfer(apiClient, 'wallet-uuid', data);

    expect(post).toHaveBeenCalledWith('/api/wallets/wallet-uuid/prepare-transfer/', data);
  });

  it('posts a Bitcoin prepare request with amountBtc to the same endpoint', () => {
    const data = { toAddress: `tb1q${'a'.repeat(38)}`, amountBtc: '0.001' };

    prepareBitcoinTransfer(apiClient, 'wallet-uuid', data, 'account-uuid');

    expect(post).toHaveBeenCalledWith('/api/wallets/wallet-uuid/prepare-transfer/', data, {
      params: { user_account: 'account-uuid' },
    });
  });

  it('posts the signed transaction to the wallet broadcast endpoint', () => {
    const data = { signedTransaction: '0200000001ab' };

    broadcastTransfer(apiClient, 'wallet-uuid', data);

    expect(post).toHaveBeenCalledWith('/api/wallets/wallet-uuid/broadcast-transfer/', data);
  });
});
