import { act, cleanup, renderHook } from '@testing-library/react-native';
import { useOrderSigning } from './useOrderSigning';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import { signEthereumTypedData } from '../../utils/softwareWallet/localSigner';
import { useOrderCancelMessage, useCancelOrder } from './useTrading';
import { snapshot, wallet } from '../../../../packages/shared/tests/fixtures/order-submissions';
import type { CancelOrderMessageResponse, TransferOrder } from '@ledova/shared';

jest.mock('uuid', () => ({ v4: () => '70000000-0000-4000-8000-000000000001' }));
jest.mock('../../services/secureKeyStorage', () => ({ getSeedPhrase: jest.fn(async () => 'synthetic-seed') }));
jest.mock('../../utils/softwareWallet/localSigner', () => ({
  signEthereumTypedData: jest.fn(async () => 'synthetic-signature'),
}));
jest.mock('./useTrading', () => ({ useOrderCancelMessage: jest.fn(), useCancelOrder: jest.fn() }));

afterEach(async () => {
  await cleanup();
});

it('preserves the existing cancellation challenge and signing callbacks without allocating a create identity', async () => {
  const order = snapshot(undefined, 'created').order!;
  const message = {
    ...snapshot().challenge!,
    purpose: 'order_cancel',
    orderUuid: order.uuid,
  } as CancelOrderMessageResponse;
  const issue = jest.fn((uuid: string, options: { onSuccess: (data: CancelOrderMessageResponse) => void }) => {
    expect(uuid).toBe(order.uuid);
    options.onSuccess(message);
  });
  const send = jest.fn((_input: unknown, options: { onSuccess: (data: TransferOrder) => void }) => {
    options.onSuccess(order);
  });
  jest.mocked(useOrderCancelMessage).mockReturnValue({ mutate: issue } as never);
  jest.mocked(useCancelOrder).mockReturnValue({ mutate: send } as never);
  const completed = jest.fn();
  const { result } = await renderHook(() =>
    useOrderSigning({ mode: 'cancel', orderUuid: order.uuid, wallet, onSuccess: completed }),
  );
  await act(async () => {
    result.current.start();
  });
  expect(result.current.step).toBe('instructions');
  await act(async () => {
    result.current.proceedToSign();
  });
  expect(getSeedPhrase).toHaveBeenCalledWith(wallet.masterFingerprint);
  expect(signEthereumTypedData).toHaveBeenCalledTimes(1);
  expect(send.mock.calls[0][0]).toEqual({ uuid: order.uuid, digest: message.digest, signature: 'synthetic-signature' });
  expect(completed).toHaveBeenCalledWith(order);
  expect(result.current.step).toBe('success');
});
