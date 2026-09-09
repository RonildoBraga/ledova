import { render } from '@testing-library/react-native';
import type { Wallet } from '@ledova/shared';

const mockWallet: Wallet = {
  uuid: 'wallet',
  userAccount: 'account',
  address: '0x' + 'a'.repeat(40),
  chain: 'base',
  verificationStatus: 'VERIFIED',
  nativeBalance: '0',
  nativeMarketValue: '0',
  marketValue: '0',
  createdAt: '2026-09-09T00:00:00Z',
  updatedAt: '2026-09-09T00:00:00Z',
};

jest.mock('@react-navigation/native', () => ({
  useNavigation: () => ({ navigate: jest.fn(), canGoBack: () => false }),
  useRoute: () => ({ params: { wallet: mockWallet } }),
}));
jest.mock('../useWalletsCrud', () => ({
  useWalletsCrud: () => ({ wallets: [mockWallet], syncingWalletIds: new Set(), isUpdating: false }),
}));
jest.mock('../../../hooks/useCurrency', () => ({ useCurrency: () => ({ formatDisplayCurrency: () => '$0.00' }) }));
jest.mock('./DeleteWalletModal', () => ({ DeleteWalletModal: () => null }));
jest.mock('./DeriveAddressModal', () => ({ DeriveAddressModal: () => null }));

import { WalletActionScreen } from './WalletActionScreen';

describe('wallet signing preferences on mobile', () => {
  it.each(['hardware', 'software'] as const)(
    'shows the %s preference as self-declared beside address verification',
    async (preference) => {
      mockWallet.signingPreference = preference;
      const view = await render(<WalletActionScreen />);
      expect(view.getByText('Signing preference')).toBeTruthy();
      expect(view.getByText(`${preference === 'hardware' ? 'Hardware' : 'Software'} (self-declared)`)).toBeTruthy();
      expect(view.getByText('Address verified')).toBeTruthy();
    },
  );

  it('shows an unspecified preference without claiming hardware or software', async () => {
    mockWallet.signingPreference = null;
    const view = await render(<WalletActionScreen />);
    expect(view.getByText('Not specified')).toBeTruthy();
    expect(view.queryByText('Hardware (self-declared)')).toBeNull();
    expect(view.queryByText('Software (self-declared)')).toBeNull();
    expect(view.getByText('Address verified')).toBeTruthy();
  });
});
