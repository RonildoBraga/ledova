import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { SwapOrder, Wallet } from '@ledova/shared';
import { SwapSigningModal } from './SwapSigningModal';
import { apiClient } from '../../../services/apiClient';
import { getSeedPhrase } from '../../../services/secureKeyStorage';
import { wallet as baseWallet, response } from '../../../../../packages/shared/tests/fixtures/order-submissions';
import fixture from '../../../../../packages/shared/tests/fixtures/swap-settlement-api.json';

jest.mock('uuid', () => ({ v4: () => '70000000-0000-4000-8000-000000000001' }));
jest.mock('../../../services/apiClient', () => ({ apiClient: jest.requireActual('axios').default.create() }));
jest.mock('../../../services/secureKeyStorage', () => ({ getSeedPhrase: jest.fn() }));
jest.mock('../../../components/qr', () => ({ QRDisplay: () => null, QRScanner: () => null }));
jest.mock('../../../components/modal', () => {
  const { View, Text, Pressable } = jest.requireActual('react-native');
  return {
    CustomModal: ({
      visible,
      children,
      onConfirm,
      confirmLabel,
    }: {
      visible: boolean;
      children: React.ReactNode;
      onConfirm?: () => void;
      confirmLabel?: string;
    }) =>
      visible ? (
        <View>
          {children}
          {onConfirm && (
            <Pressable onPress={onConfirm}>
              <Text>{confirmLabel}</Text>
            </Pressable>
          )}
        </View>
      ) : null,
  };
});
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false, gcTime: Infinity } },
});
afterEach(async () => {
  await cleanup();
  queryClient.clear();
});

it('keeps the explicit V0 route usable through its original helpers and software signer', async () => {
  const wallet: Wallet = {
    ...baseWallet,
    uuid: fixture.get_body.walletUuid,
    address: fixture.addresses[0],
    userAccount: fixture.get_body.ownerAccountUuid,
    masterFingerprint: '12345678',
    derivationPath: fixture.paths[0],
    signingPreference: 'software',
  };
  const swap: SwapOrder = {
    ...fixture.get_body.swapOrder,
    status: 'created',
    settlementProtocolVersion: 0,
    settlementContext: null,
    settlementDigest: '',
  };
  jest.mocked(getSeedPhrase).mockResolvedValue(fixture.mnemonic);
  const signed = jest.fn();
  apiClient.defaults.adapter = async (config) => {
    if (config.method === 'post') {
      signed(config);
      return response(config, swap);
    }
    if (config.url?.endsWith('/swap/')) return response(config, { ...fixture.get_body, swapOrder: swap });
    return response(config, { needsApproval: false, tokenSymbol: 'TUSD', currentAllowance: '99999999999999999999' });
  };
  const view = await render(
    <QueryClientProvider client={queryClient}>
      <SwapSigningModal visible swap={swap} wallet={wallet} onClose={() => {}} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(view.getByText('Sign with Biometric')).toBeTruthy());
  await fireEvent.press(view.getByText('Sign with Biometric'));
  await act(async () => {});
  await waitFor(() => expect(signed).toHaveBeenCalledTimes(1));
  const request = signed.mock.calls[0][0];
  expect(request.url).toBe(`/api/v1/trading/orders/${swap.sellOrderUuid}/swap/sign/`);
  expect(JSON.parse(request.data)).toEqual({ signature: fixture.signatures[0], signer_address: fixture.addresses[0] });
});
