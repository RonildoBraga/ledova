// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type { CancelOrderMessageResponse, TransferOrder } from '@ledova/shared';
import { OrderSigningFlow } from './components/OrderSigningFlow';
import { useOrderCancelMessage, useCancelOrder } from './useTrading';
import { snapshot, wallet } from '../../../../packages/shared/tests/fixtures/order-submissions';

vi.mock('@components/SeedPhraseInput', () => ({
  SeedPhraseInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <input aria-label="Synthetic seed" value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}));
vi.mock('@components/qr', () => ({
  useQRScanner: () => ({ error: null, stopScanner: vi.fn() }),
  QRScannerView: () => null,
}));
vi.mock('@keystonehq/animated-qr', () => ({ AnimatedQRCode: () => null }));
vi.mock('@utils/softwareWallet/localSigner', async () => {
  const f = await import('../../../../packages/shared/tests/fixtures/order-submissions');
  return { deriveAddress: () => f.wallet.address, signEthereumTypedData: async () => 'synthetic-signature' };
});
vi.mock('./useTrading', () => ({ useOrderCancelMessage: vi.fn(), useCancelOrder: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it('retains the existing cancellation modal callbacks and cancellation-only payload', async () => {
  const order = snapshot(undefined, 'created').order!;
  const message = {
    ...snapshot().challenge!,
    purpose: 'order_cancel',
    orderUuid: order.uuid,
  } as CancelOrderMessageResponse;
  const issue = vi.fn((uuid: string, options: { onSuccess: (data: CancelOrderMessageResponse) => void }) => {
    expect(uuid).toBe(order.uuid);
    options.onSuccess(message);
  });
  const send = vi.fn((_input: unknown, options: { onSuccess: (data: TransferOrder) => void }) => {
    options.onSuccess(order);
  });
  vi.mocked(useOrderCancelMessage).mockReturnValue({ mutate: issue } as never);
  vi.mocked(useCancelOrder).mockReturnValue({ mutate: send } as never);
  const complete = vi.fn();
  render(
    <OrderSigningFlow
      isOpen
      mode="cancel"
      orderUuid={order.uuid}
      wallet={wallet}
      onClose={() => {}}
      onSuccess={complete}
    />,
  );
  fireEvent.click(await screen.findByText('Continue'));
  fireEvent.change(screen.getByLabelText('Synthetic seed'), { target: { value: 'synthetic-seed' } });
  fireEvent.click(screen.getByText('Sign'));
  await waitFor(() => expect(complete).toHaveBeenCalledWith(order));
  expect(send.mock.calls[0][0]).toEqual({ uuid: order.uuid, digest: message.digest, signature: 'synthetic-signature' });
  expect(screen.getByText('Order Cancelled!')).toBeTruthy();
});
