// @vitest-environment jsdom

import { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PrepareBitcoinTransferResponse } from '@ledova/shared-types';
import { BitcoinSignStep, INVALID_SIGNED_HEX_MESSAGE } from './BitcoinSignStep';

const prepared: PrepareBitcoinTransferResponse = {
  fromAddress: `tb1q${'a'.repeat(38)}`,
  toAddress: `tb1q${'b'.repeat(38)}`,
  amountBtc: '0.001',
  amountSatoshis: 100000,
  feePerByte: '12',
  estimatedTxSize: 250,
  feeSatoshis: 3000,
  feeBtc: '0.00003',
  totalCostBtc: '0.00103',
  network: 'BTC',
};

function Harness({ onBroadcast }: { onBroadcast: (hex: string) => void }) {
  const [signedTransaction, setSignedTransaction] = useState('');
  return (
    <BitcoinSignStep
      prepared={prepared}
      signedTransaction={signedTransaction}
      onSignedTransactionChange={setSignedTransaction}
      onCancel={() => {}}
      onBroadcast={onBroadcast}
    />
  );
}

describe('BitcoinSignStep', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('shows what to sign and keeps Broadcast disabled until a hex is pasted', () => {
    render(<Harness onBroadcast={vi.fn()} />);

    expect(screen.getByText('0.001 BTC')).toBeDefined();
    expect(screen.getByText('12 sat/vB')).toBeDefined();
    expect(screen.getByText('250 vB')).toBeDefined();
    expect(screen.getByText('0.00103 BTC')).toBeDefined();
    expect(screen.getByText(prepared.toAddress)).toBeDefined();
    expect((screen.getByRole('button', { name: 'Broadcast' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('broadcasts the pasted hex with the 0x prefix and whitespace removed', () => {
    const onBroadcast = vi.fn();
    render(<Harness onBroadcast={onBroadcast} />);

    fireEvent.change(screen.getByLabelText('Signed transaction (hex)'), { target: { value: ' 0x0200 0000 01AB \n' } });
    fireEvent.click(screen.getByRole('button', { name: 'Broadcast' }));

    expect(onBroadcast).toHaveBeenCalledWith('0200000001ab');
    expect(screen.queryByText(INVALID_SIGNED_HEX_MESSAGE)).toBeNull();
  });

  it('rejects input that is not a hex byte string and does not broadcast', () => {
    const onBroadcast = vi.fn();
    render(<Harness onBroadcast={onBroadcast} />);

    fireEvent.change(screen.getByLabelText('Signed transaction (hex)'), { target: { value: '0200000001a' } });
    fireEvent.click(screen.getByRole('button', { name: 'Broadcast' }));

    expect(onBroadcast).not.toHaveBeenCalled();
    expect(screen.getByText(INVALID_SIGNED_HEX_MESSAGE)).toBeDefined();
  });
});
