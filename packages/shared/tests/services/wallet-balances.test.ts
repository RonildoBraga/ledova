import type { AxiosInstance } from 'axios';
import { getWalletHoldings } from '../../src/services/wallet-balances';

describe('wallet balance services', () => {
  const get = jest.fn();
  const apiClient = { get } as unknown as AxiosInstance;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('gets wallet holdings without query parameters', () => {
    getWalletHoldings(apiClient, 'wallet-uuid');

    expect(get).toHaveBeenCalledWith('/api/wallets/wallet-uuid/holdings/');
  });
});
