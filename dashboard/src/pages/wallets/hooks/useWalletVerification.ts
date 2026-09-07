import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  requestVerificationChallenge,
  verifyWalletSignature,
  BLOCKCHAIN,
  getWalletVerificationEvmChainId,
} from '@ledova/shared';
import type { Wallet } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { encodeEthereumMessage, encodeBitcoinMessage } from '@utils/keystone/urEncoder';
import { DEFAULT_EVM_DERIVATION_PATH, deriveAddress, signEthereumMessage } from '@utils/softwareWallet/localSigner';

export type VerificationStep = 'instructions' | 'show-challenge-qr' | 'scan-signature' | 'sign-software' | 'success';

export type VerificationMode = 'hardware' | 'software';

interface UseWalletVerificationReturn {
  verificationStep: VerificationStep;
  verificationChallenge: string | null;
  challengeQrData: string | null;
  verificationError: string | null;
  verificationSuccess: boolean;

  isRequestingChallenge: boolean;
  isVerifying: boolean;

  isSigningWithSeedPhrase: boolean;

  startVerification: (wallet: Wallet, mode?: VerificationMode) => Promise<void>;
  proceedToScanSignature: () => void;
  handleSignatureScanned: (signature: string) => Promise<void>;
  signWithSeedPhrase: (seedPhrase: string) => Promise<void>;
  goBack: () => void;
  reset: () => void;
}

export function useWalletVerification(): UseWalletVerificationReturn {
  const queryClient = useQueryClient();

  const [verificationStep, setVerificationStep] = useState<VerificationStep>('instructions');
  const [verificationChallenge, setVerificationChallenge] = useState<string | null>(null);
  const [challengeQrData, setChallengeQrData] = useState<string | null>(null);
  const [verificationError, setVerificationError] = useState<string | null>(null);
  const [verificationSuccess, setVerificationSuccess] = useState(false);
  const [currentWallet, setCurrentWallet] = useState<Wallet | null>(null);
  const [isSigningWithSeedPhrase, setIsSigningWithSeedPhrase] = useState(false);

  const challengeMutation = useMutation({
    mutationFn: async ({ wallet }: { wallet: Wallet; mode: VerificationMode }) => {
      const response = await requestVerificationChallenge(apiClient, wallet.uuid);
      return response.data;
    },
    onSuccess: (data, { wallet, mode }) => {
      const challenge = data.challenge;
      setVerificationChallenge(challenge);

      if (mode === 'software') {
        setVerificationStep('sign-software');
        return;
      }

      let qrData: { urString: string } | null = null;

      const evmChainId = getWalletVerificationEvmChainId(wallet.chain);

      if (evmChainId !== null) {
        qrData = encodeEthereumMessage(
          wallet.address,
          challenge,
          wallet.derivationPath,
          wallet.masterFingerprint,
          evmChainId,
        );
      } else if (wallet.chain === BLOCKCHAIN.BITCOIN) {
        qrData = encodeBitcoinMessage(wallet.address, challenge, wallet.derivationPath, wallet.masterFingerprint);
      }

      if (qrData) {
        setChallengeQrData(qrData.urString);
        setVerificationStep('show-challenge-qr');
      } else {
        setVerificationError('Failed to generate QR code. Missing wallet derivation data.');
      }
    },
    onError: () => {
      setVerificationError('Failed to request verification challenge. Please try again.');
    },
  });

  const verifyMutation = useMutation({
    mutationFn: async ({ walletUuid, signature }: { walletUuid: string; signature: string }) => {
      const response = await verifyWalletSignature(apiClient, walletUuid, { signature });
      return response.data;
    },
    onSuccess: () => {
      setVerificationSuccess(true);
      setVerificationStep('success');

      queryClient.invalidateQueries({ queryKey: ['wallets'] });
      queryClient.invalidateQueries({ queryKey: ['home-wallets'] });
    },
    onError: () => {
      setVerificationError('Signature verification failed. Please try again.');
    },
  });

  const startVerification = useCallback(
    async (wallet: Wallet, mode: VerificationMode = 'hardware') => {
      setCurrentWallet(wallet);
      setVerificationError(null);
      setVerificationSuccess(false);
      setChallengeQrData(null);
      setVerificationChallenge(null);

      if (mode === 'hardware' && (!wallet.derivationPath || !wallet.masterFingerprint)) {
        setVerificationError('This wallet cannot be verified with a hardware wallet. Missing hardware wallet data.');
        return;
      }

      challengeMutation.mutate({ wallet, mode });
    },
    [challengeMutation],
  );

  const proceedToScanSignature = useCallback(() => {
    setVerificationStep('scan-signature');
    setVerificationError(null);
  }, []);

  const handleSignatureScanned = useCallback(
    async (signature: string) => {
      if (!currentWallet) return;

      setVerificationError(null);
      verifyMutation.mutate({ walletUuid: currentWallet.uuid, signature });
    },
    [currentWallet, verifyMutation],
  );

  const signWithSeedPhrase = useCallback(
    async (seedPhrase: string) => {
      if (!currentWallet || !verificationChallenge) return;

      const phrase = seedPhrase.trim();
      const derivationPath = currentWallet.derivationPath || DEFAULT_EVM_DERIVATION_PATH;

      setVerificationError(null);
      setIsSigningWithSeedPhrase(true);

      try {
        const derived = deriveAddress(phrase, derivationPath);

        if (derived.toLowerCase() !== currentWallet.address.toLowerCase()) {
          setVerificationError(`Seed phrase does not match this wallet address at ${derivationPath}.`);
          return;
        }

        const signature = await signEthereumMessage(phrase, derivationPath, verificationChallenge);
        verifyMutation.mutate({ walletUuid: currentWallet.uuid, signature });
      } catch {
        setVerificationError('Could not sign with that seed phrase. Check that it is a valid 12 or 24 word phrase.');
      } finally {
        setIsSigningWithSeedPhrase(false);
      }
    },
    [currentWallet, verificationChallenge, verifyMutation],
  );

  const goBack = useCallback(() => {
    if (verificationStep === 'sign-software') {
      setVerificationStep('instructions');
    } else if (verificationStep === 'scan-signature') {
      setVerificationStep('show-challenge-qr');
    } else if (verificationStep === 'show-challenge-qr') {
      setVerificationStep('instructions');
    }
    setVerificationError(null);
  }, [verificationStep]);

  const reset = useCallback(() => {
    setVerificationStep('instructions');
    setVerificationChallenge(null);
    setChallengeQrData(null);
    setVerificationError(null);
    setVerificationSuccess(false);
    setCurrentWallet(null);
    setIsSigningWithSeedPhrase(false);
  }, []);

  return {
    verificationStep,
    verificationChallenge,
    challengeQrData,
    verificationError,
    verificationSuccess,
    isRequestingChallenge: challengeMutation.isPending,
    isVerifying: verifyMutation.isPending,
    isSigningWithSeedPhrase,
    startVerification,
    proceedToScanSignature,
    handleSignatureScanned,
    signWithSeedPhrase,
    goBack,
    reset,
  };
}
