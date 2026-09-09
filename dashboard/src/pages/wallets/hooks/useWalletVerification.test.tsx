// @vitest-environment jsdom

import type { PropsWithChildren } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { verifyMessage } from 'ethers';
import { requestVerificationChallenge, verifyWalletSignature } from '@ledova/shared';
import type { Wallet } from '@ledova/shared';
import { useWalletVerification } from './useWalletVerification';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@ledova/shared', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@ledova/shared')>()),
  requestVerificationChallenge: vi.fn(),
  verifyWalletSignature: vi.fn(),
}));

const requestChallengeMock = vi.mocked(requestVerificationChallenge);
const verifySignatureMock = vi.mocked(verifyWalletSignature);

const HARDHAT_MNEMONIC = 'test test test test test test test test test test test junk';
const HARDHAT_ACCOUNT_0 = '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266';
const HARDHAT_ACCOUNT_1 = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8';
const CHALLENGE = 'Ledova Wallet Verification\n\nAddress: 0xf39F\nTimestamp: 1\nNonce: abc\n';

const typedWallet = (address: string, overrides: Partial<Wallet> = {}) =>
  ({
    uuid: 'wallet-uuid',
    userAccount: 'account-uuid',
    address,
    chain: 'base',
    verificationStatus: 'PENDING',
    nativeBalance: '0',
    nativeMarketValue: '0',
    marketValue: '0',
    ...overrides,
  }) as Wallet;

const createHarness = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper };
};

describe('useWalletVerification', () => {
  beforeEach(() => {
    requestChallengeMock.mockReset();
    verifySignatureMock.mockReset();
    requestChallengeMock.mockResolvedValue({ data: { challenge: CHALLENGE } } as never);
    verifySignatureMock.mockResolvedValue({ data: { success: true } } as never);
  });

  it('refuses a hardware verification when the wallet carries no hardware data', async () => {
    const { wrapper } = createHarness();
    const { result } = renderHook(() => useWalletVerification(), { wrapper });

    await act(async () => {
      await result.current.startVerification(typedWallet(HARDHAT_ACCOUNT_0), 'hardware');
    });

    expect(result.current.verificationError).toContain('Missing hardware wallet data');
    expect(requestChallengeMock).not.toHaveBeenCalled();
  });

  it('accepts the same wallet for seed-phrase verification and asks for a challenge', async () => {
    const { wrapper } = createHarness();
    const { result } = renderHook(() => useWalletVerification(), { wrapper });

    await act(async () => {
      await result.current.startVerification(typedWallet(HARDHAT_ACCOUNT_0), 'software');
    });

    await waitFor(() => expect(result.current.verificationStep).toBe('sign-software'));
    expect(requestChallengeMock).toHaveBeenCalledTimes(1);
    expect(result.current.verificationError).toBeNull();
  });

  it('refuses a seed phrase that does not derive the wallet address, without submitting it', async () => {
    const { wrapper } = createHarness();
    const { result } = renderHook(() => useWalletVerification(), { wrapper });

    await act(async () => {
      await result.current.startVerification(typedWallet(HARDHAT_ACCOUNT_1), 'software');
    });
    await waitFor(() => expect(result.current.verificationStep).toBe('sign-software'));

    await act(async () => {
      await result.current.signWithSeedPhrase(HARDHAT_MNEMONIC);
    });

    expect(result.current.verificationError).toContain('does not match this wallet address');
    expect(verifySignatureMock).not.toHaveBeenCalled();
  });

  it('signs the challenge locally and submits a 0x signature for the matching address', async () => {
    const { wrapper } = createHarness();
    const { result } = renderHook(() => useWalletVerification(), { wrapper });

    await act(async () => {
      await result.current.startVerification(typedWallet(HARDHAT_ACCOUNT_0), 'software');
    });
    await waitFor(() => expect(result.current.verificationStep).toBe('sign-software'));

    await act(async () => {
      await result.current.signWithSeedPhrase(HARDHAT_MNEMONIC);
    });

    await waitFor(() => expect(verifySignatureMock).toHaveBeenCalledTimes(1));

    const [, walletUuid, payload] = verifySignatureMock.mock.calls[0];
    expect(walletUuid).toBe('wallet-uuid');
    expect(payload.signature).toMatch(/^0x[0-9a-f]{130}$/i);
    expect(verifyMessage(CHALLENGE, payload.signature).toLowerCase()).toBe(HARDHAT_ACCOUNT_0.toLowerCase());

    await waitFor(() => expect(result.current.verificationStep).toBe('success'));
  });

  it('honours an explicit derivation path stored on the wallet', async () => {
    const { wrapper } = createHarness();
    const { result } = renderHook(() => useWalletVerification(), { wrapper });
    const wallet = typedWallet(HARDHAT_ACCOUNT_1, { derivationPath: "m/44'/60'/0'/0/1" });

    await act(async () => {
      await result.current.startVerification(wallet, 'software');
    });
    await waitFor(() => expect(result.current.verificationStep).toBe('sign-software'));

    await act(async () => {
      await result.current.signWithSeedPhrase(HARDHAT_MNEMONIC);
    });

    await waitFor(() => expect(verifySignatureMock).toHaveBeenCalledTimes(1));
  });
});
