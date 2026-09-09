import type { ComponentProps } from 'react';
import { render } from '@testing-library/react-native';
import { TransferFormScreen } from './TransferFormScreen';
import { useTransfers } from '../useTransfers';
import { encodeEthereumTransaction } from '../../../utils/keystone/urEncoder';

jest.mock('../useTransfers', () => ({ useTransfers: jest.fn() }));
jest.mock('../../../utils/keystone/urEncoder', () => ({
  encodeEthereumTransaction: jest.fn(() => ({ urString: 'ur:base-transaction' })),
}));
jest.mock('../../../utils/keystone/urDecoder', () => ({ decodeKeystoneSignature: jest.fn() }));
jest.mock('../../../components/GradientBackground', () => ({
  GradientBackground: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('../../../components/qr', () => ({ QRScanner: () => null, QRDisplay: () => null }));
jest.mock('./SoftwareSignTransaction', () => ({ SoftwareSignTransaction: () => null }));
jest.mock('./SignTransaction', () => ({
  SignTransaction: ({ urEncodedTransaction }: { urEncodedTransaction: string | null }) => {
    const { Text } = jest.requireActual<typeof import('react-native')>('react-native');
    return <Text>{urEncodedTransaction || 'No QR'}</Text>;
  },
}));

it('passes the Base transaction and wallet derivation data to the hardware encoder', async () => {
  const wallet = {
    uuid: 'base-wallet',
    chain: 'base',
    address: `0x${'1'.repeat(40)}`,
    derivationPath: "m/44'/60'/0'/0/0",
    masterFingerprint: '12345678',
  };
  const transaction = { chainId: 84532, nonce: 1, to: `0x${'2'.repeat(40)}`, value: 1, gas: 21000 };
  jest.mocked(useTransfers).mockReturnValue({
    wallet,
    step: 'sign',
    transactionData: { transaction },
    selectWallet: jest.fn(),
    reset: jest.fn(),
  } as unknown as ReturnType<typeof useTransfers>);
  const route = { key: 'transfer', name: 'TransferDetails', params: { wallet } } as ComponentProps<
    typeof TransferFormScreen
  >['route'];
  const navigation = { goBack: jest.fn() } as unknown as ComponentProps<typeof TransferFormScreen>['navigation'];
  const view = await render(<TransferFormScreen route={route} navigation={navigation} />);
  expect(view.getByText('ur:base-transaction')).toBeTruthy();
  expect(encodeEthereumTransaction).toHaveBeenCalledWith(
    wallet.address,
    transaction,
    wallet.derivationPath,
    wallet.masterFingerprint,
  );
});
