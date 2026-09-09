// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import type { Wallet } from '@ledova/shared';
import { WalletItem } from './WalletItem';

vi.mock('@hooks/useCurrency', () => ({ useCurrency: () => ({ formatDisplayCurrency: () => '$0.00' }) }));

const wallet: Wallet = {
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

afterEach(cleanup);

describe('wallet signing preferences on the dashboard', () => {
  it.each(['hardware', 'software'] as const)(
    'labels %s as self-declared independently of address verification',
    (signingPreference) => {
      const view = render(
        <WalletItem wallet={{ ...wallet, signingPreference }} isSelected={false} onSelect={() => {}} />,
      );
      expect(
        view.getByLabelText(`${signingPreference === 'hardware' ? 'Hardware' : 'Software'} (self-declared)`),
      ).toBeTruthy();
      expect(view.getByLabelText('Wallet address verified')).toBeTruthy();
    },
  );

  it('does not invent a type badge for an unspecified preference', () => {
    const view = render(
      <WalletItem wallet={{ ...wallet, signingPreference: null }} isSelected={false} onSelect={() => {}} />,
    );
    expect(view.queryByLabelText('Hardware (self-declared)')).toBeNull();
    expect(view.queryByLabelText('Software (self-declared)')).toBeNull();
    expect(view.getByLabelText('Wallet address verified')).toBeTruthy();
  });
});
