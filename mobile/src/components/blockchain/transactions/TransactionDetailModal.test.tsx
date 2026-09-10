import { render } from '@testing-library/react-native';
import type { Transaction } from '@ledova/shared';
import { TransactionDetailModal } from './TransactionDetailModal';

const transaction: Transaction = {
  uuid: 'synthetic-transaction',
  createdAt: '2026-09-01T10:00:00Z',
  txHash: '0x' + '17'.repeat(32),
  chain: 'base',
  fromAddress: '0x' + 'ab'.repeat(20),
  toAddress: '0x' + 'cd'.repeat(20),
  walletAddress: '0x' + 'ab'.repeat(20),
  wallet: 'synthetic-wallet',
  asset: 'synthetic-asset',
  assetSymbol: 'ETH',
  amount: '2',
  blockTimestamp: '2026-09-01T10:00:00Z',
};

it.each([
  ['success', '✓ Success'],
  ['confirmed', '✓ Confirmed'],
  ['pending', 'Pending'],
  ['failed', '✗ Failed'],
  ['replaced', 'Replaced'],
  ['reorged', 'Confirmation reversed'],
  ['unrecognized', 'Unknown'],
  ['constructor', 'Unknown'],
  [undefined, 'Unknown'],
] as const)('shows %s as %s in the transaction details', async (status, label) => {
  const view = await render(
    <TransactionDetailModal visible transaction={{ ...transaction, status }} onClose={() => {}} />,
  );
  expect(view.getByText(label)).toBeTruthy();
  if (status !== 'failed') expect(view.queryByText('✗ Failed')).toBeNull();
});

it('updates a pending import when its receipt confirms', async () => {
  const view = await render(
    <TransactionDetailModal visible transaction={{ ...transaction, status: 'pending' }} onClose={() => {}} />,
  );
  expect(view.getByText('Pending')).toBeTruthy();
  await view.rerender(
    <TransactionDetailModal visible transaction={{ ...transaction, status: 'confirmed' }} onClose={() => {}} />,
  );
  expect(view.getByText('✓ Confirmed')).toBeTruthy();
  expect(view.queryByText('Pending')).toBeNull();
  expect(view.queryByText('✗ Failed')).toBeNull();
});
