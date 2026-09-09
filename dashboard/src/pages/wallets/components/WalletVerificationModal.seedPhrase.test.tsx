// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Wallet } from '@ledova/shared';
import { WalletVerificationModal } from './WalletVerificationModal';

const signWithSeedPhrase = vi.fn();

const hookState = {
  verificationStep: 'sign-software' as string,
  verificationChallenge: 'challenge',
  challengeQrData: null,
  verificationError: null as string | null,
  verificationSuccess: false,
  isRequestingChallenge: false,
  isVerifying: false,
  isSigningWithSeedPhrase: false,
  startVerification: vi.fn(),
  proceedToScanSignature: vi.fn(),
  handleSignatureScanned: vi.fn(),
  signWithSeedPhrase,
  goBack: vi.fn(),
  reset: vi.fn(),
};

vi.mock('../hooks/useWalletVerification', () => ({
  useWalletVerification: () => hookState,
}));

vi.mock('@components/qr', () => ({
  useQRScanner: () => ({ error: null, stopScanner: vi.fn() }),
  QRScannerView: () => null,
}));

const wallet = {
  uuid: 'wallet-uuid',
  address: '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266',
  chain: 'base',
  verificationStatus: 'PENDING',
} as Wallet;

const PHRASE = 'test test test test test test test test test test test junk';

const seedPhraseBox = () => screen.getByPlaceholderText(/12 or 24 word seed phrase/i) as HTMLTextAreaElement;

describe('WalletVerificationModal, signing with a seed phrase', () => {
  beforeEach(() => {
    signWithSeedPhrase.mockReset();
    signWithSeedPhrase.mockResolvedValue(undefined);
    hookState.verificationError = null;
  });

  afterEach(() => {
    cleanup();
  });

  it('hands the phrase to the signer and clears it from the page in the same click', () => {
    render(<WalletVerificationModal isOpen wallet={wallet} onClose={() => {}} />);

    fireEvent.change(seedPhraseBox(), { target: { value: PHRASE } });
    expect(seedPhraseBox().value).toBe(PHRASE);

    fireEvent.click(screen.getByRole('button', { name: /sign and verify/i }));

    expect(signWithSeedPhrase).toHaveBeenCalledWith(PHRASE);
    expect(seedPhraseBox().value).toBe('');
  });

  it('says the phrase was cleared when signing failed and the box is empty', () => {
    hookState.verificationError = 'Seed phrase does not match this wallet address.';
    render(<WalletVerificationModal isOpen wallet={wallet} onClose={() => {}} />);

    expect(screen.getByText(/enter it again to retry/i)).toBeTruthy();

    fireEvent.change(seedPhraseBox(), { target: { value: PHRASE } });
    expect(screen.queryByText(/enter it again to retry/i)).toBeNull();
  });
});
