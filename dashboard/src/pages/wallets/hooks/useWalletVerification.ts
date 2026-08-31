import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { requestVerificationChallenge, verifyWalletSignature } from '@ledova/shared-services';
import { BLOCKCHAIN, getWalletVerificationEvmChainId } from '@ledova/shared-constants';
import type { Wallet } from '@ledova/shared-types';
import apiClient from '@services/apiClient';
import { encodeEthereumMessage, encodeBitcoinMessage } from '@utils/keystone/urEncoder';

export type VerificationStep = 'instructions' | 'show-challenge-qr' | 'scan-signature' | 'success';

interface UseWalletVerificationReturn {
  // State
  verificationStep: VerificationStep;
  verificationChallenge: string | null;
  challengeQrData: string | null;
  verificationError: string | null;
  verificationSuccess: boolean;

  // Loading states
  isRequestingChallenge: boolean;
  isVerifying: boolean;

  // Actions
  startVerification: (wallet: Wallet) => Promise<void>;
  proceedToScanSignature: () => void;
  handleSignatureScanned: (signature: string) => Promise<void>;
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

  // Request challenge mutation
  const challengeMutation = useMutation({
    mutationFn: async (wallet: Wallet) => {
      const response = await requestVerificationChallenge(apiClient, wallet.uuid);
      return response.data;
    },
    onSuccess: (data, wallet) => {
      const challenge = data.challenge;
      setVerificationChallenge(challenge);

      // Encode the challenge as a QR code based on chain type
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

  // Verify signature mutation
  const verifyMutation = useMutation({
    mutationFn: async ({ walletUuid, signature }: { walletUuid: string; signature: string }) => {
      const response = await verifyWalletSignature(apiClient, walletUuid, { signature });
      return response.data;
    },
    onSuccess: () => {
      setVerificationSuccess(true);
      setVerificationStep('success');
      // Invalidate wallets query to refresh the list
      queryClient.invalidateQueries({ queryKey: ['wallets'] });
      queryClient.invalidateQueries({ queryKey: ['home-wallets'] });
    },
    onError: () => {
      setVerificationError('Signature verification failed. Please try again.');
    },
  });

  const startVerification = useCallback(
    async (wallet: Wallet) => {
      setCurrentWallet(wallet);
      setVerificationError(null);
      setVerificationSuccess(false);
      setChallengeQrData(null);
      setVerificationChallenge(null);

      // Check if wallet has required derivation data
      if (!wallet.derivationPath || !wallet.masterFingerprint) {
        setVerificationError('This wallet cannot be verified. Missing hardware wallet data.');
        return;
      }

      challengeMutation.mutate(wallet);
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

  const goBack = useCallback(() => {
    if (verificationStep === 'scan-signature') {
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
  }, []);

  return {
    verificationStep,
    verificationChallenge,
    challengeQrData,
    verificationError,
    verificationSuccess,
    isRequestingChallenge: challengeMutation.isPending,
    isVerifying: verifyMutation.isPending,
    startVerification,
    proceedToScanSignature,
    handleSignatureScanned,
    goBack,
    reset,
  };
}
