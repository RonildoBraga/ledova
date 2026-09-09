import { fireEvent, render } from '@testing-library/react-native';
import type { HardwareWalletImport } from '@ledova/shared';
import { apiClient } from '../../../services/apiClient';
import { extractFromKeystoneQR } from '../../../utils/keystone/bcurDecoder';
import { HardwareAccountSelector } from './HardwareAccountSelector';

jest.mock('../../../services/apiClient', () => ({ apiClient: { post: jest.fn() } }));
jest.mock('../../../utils/keystone/bcurDecoder', () => ({ extractFromKeystoneQR: jest.fn() }));

const post = apiClient.post as jest.Mock;
const address = '0x' + 'a'.repeat(40);
const data: HardwareWalletImport = {
  addresses: [{ address, networkType: 'ETH', addressIndex: 0, derivationPath: "m/44'/60'/0'/0/0" }],
  masterFingerprint: 'fingerprint',
  parentKeys: [{ parentPublicKey: 'public', parentChainCode: 'chain', parentDerivationPath: "m/44'/60'/0'/0" }],
};

beforeEach(() => {
  post.mockReset();
  (extractFromKeystoneQR as jest.Mock).mockReturnValue(data);
});

it('shows the Base balance and imports on Base after changing the network', async () => {
  post.mockImplementation(async (_url, body) => ({
    data: {
      userAccount: body.userAccount,
      chain: body.chain,
      balances: { [address]: body.chain === 'base' ? '2' : '5' },
    },
  }));
  const selected = jest.fn();
  const view = await render(
    <HardwareAccountSelector
      urString="synthetic-qr"
      userAccountUuid="account"
      onSelectAccounts={selected}
      onCancel={jest.fn()}
    />,
  );
  await view.findByText('5 ETH');
  await fireEvent.press(view.getByLabelText('Base network'));
  await view.findByText('2 ETH');
  await fireEvent.press(view.getByText('Import Wallet'));
  expect(selected).toHaveBeenCalledWith([{ ...data.addresses[0], networkType: 'BASE' }], {
    ...data,
    addresses: [{ ...data.addresses[0], networkType: 'BASE' }],
  });
});

it('displays unavailable balances and prevents imports without an account', async () => {
  const selected = jest.fn();
  const view = await render(
    <HardwareAccountSelector
      urString="synthetic-qr"
      userAccountUuid={undefined}
      onSelectAccounts={selected}
      onCancel={jest.fn()}
    />,
  );
  await view.findByText('Unavailable');
  await fireEvent.press(view.getByText('Import Wallet'));
  expect(post).not.toHaveBeenCalled();
  expect(selected).not.toHaveBeenCalled();
});
