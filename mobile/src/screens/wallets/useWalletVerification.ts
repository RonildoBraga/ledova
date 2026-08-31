import { useState, useCallback, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { requestVerificationChallenge, verifyWalletSignature } from '@ledova/shared-services';
import { getErrorMessage } from '@ledova/shared-utils';
import type { Wallet, VerifyWalletRequest } from '@ledova/shared-types';
import { apiClient } from '../../services/apiClient';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import { signEthereumMessage, signBitcoinMessage } from '../../utils/softwareWallet';
import { isBitcoinChain, getChainShortCode } from '@ledova/shared-constants';

type VerificationStep = 'instructions' | 'show-challenge-qr' | 'scan-signature';

interface UseWalletVerificationProps {
  wallet: Wallet;
}

export function useWalletVerification({ wallet }: UseWalletVerificationProps) {
  const queryClient = useQueryClient();
  const { selectedAccount } = useUserPreferences();

  const [verificationChallenge, setVerificationChallenge] = useState<string | null>(null);
  const [verificationStep, setVerificationStep] = useState<VerificationStep>('instructions');
  const [autoVerifyError, setAutoVerifyError] = useState<string | null>(null);
  const [autoVerifySuccess, setAutoVerifySuccess] = useState(false);
  const [autoVerifyLoading, setAutoVerifyLoading] = useState(false);
  const autoVerifyingRef = useRef(false);

  const requestChallengeMutation = useMutation({
    mutationFn: () => requestVerificationChallenge(apiClient, wallet.uuid, selectedAccount?.uuid),
    onSuccess: (response) => {
      setVerificationChallenge(response.data.challenge);
      setVerificationStep('show-challenge-qr');
    },
  });

  const verifySignatureMutation = useMutation({
    mutationFn: (data: VerifyWalletRequest) =>
      verifyWalletSignature(apiClient, wallet.uuid, data, selectedAccount?.uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] });
    },
  });

  const requestChallenge = useCallback(() => {
    requestChallengeMutation.mutate();
  }, [requestChallengeMutation]);

  const proceedToScanSignature = useCallback(() => {
    setVerificationStep('scan-signature');
  }, []);

  const goBackVerificationStep = useCallback(() => {
    if (verificationStep === 'scan-signature') {
      setVerificationStep('show-challenge-qr');
    } else if (verificationStep === 'show-challenge-qr') {
      setVerificationStep('instructions');
    }
  }, [verificationStep]);

  const verifySignature = useCallback(
    (signature: string) => {
      if (!verificationChallenge) return;
      verifySignatureMutation.mutate({ signature });
    },
    [verificationChallenge, verifySignatureMutation],
  );

  /**
   * Auto-verify for software wallets:
   * 1. Request challenge from backend
   * 2. Sign challenge locally with biometric auth
   * 3. Submit signature to backend
   */
  const autoVerify = useCallback(async () => {
    if (autoVerifyingRef.current) return;
    if (wallet.walletType !== 'software') return;
    if (!wallet.derivationPath || !wallet.masterFingerprint) return;

    autoVerifyingRef.current = true;
    setAutoVerifyError(null);
    setAutoVerifySuccess(false);
    setAutoVerifyLoading(true);

    try {
      // Step 1: Request challenge
      const challengeResponse = await requestVerificationChallenge(apiClient, wallet.uuid, selectedAccount?.uuid);
      const challenge = challengeResponse.data.challenge;
      setVerificationChallenge(challenge);

      // Step 2: Retrieve seed and sign locally
      const seedId = wallet.masterFingerprint;
      const mnemonic = await getSeedPhrase(seedId);
      if (!mnemonic) {
        setAutoVerifyLoading(false);
        autoVerifyingRef.current = false;
        return;
      }

      const chainShortCode = getChainShortCode(wallet.chain);
      const signature = isBitcoinChain(chainShortCode)
        ? await signBitcoinMessage(mnemonic, wallet.derivationPath, challenge)
        : await signEthereumMessage(mnemonic, wallet.derivationPath, challenge);

      // Step 3: Submit signature directly (avoid stale mutation closure)
      await verifyWalletSignature(apiClient, wallet.uuid, { signature }, selectedAccount?.uuid);
      queryClient.refetchQueries({ queryKey: ['wallets'] });
      setAutoVerifySuccess(true);
    } catch (err) {
      setAutoVerifyError(err instanceof Error ? err.message : 'Verification failed');
    } finally {
      setAutoVerifyLoading(false);
      autoVerifyingRef.current = false;
    }
  }, [
    wallet.uuid,
    wallet.walletType,
    wallet.chain,
    wallet.derivationPath,
    wallet.masterFingerprint,
    selectedAccount?.uuid,
    queryClient,
  ]);

  const reset = useCallback(() => {
    setVerificationChallenge(null);
    setVerificationStep('instructions');
  }, []);

  return {
    // State
    verificationChallenge,
    verificationStep,

    // Loading states
    isRequestingChallenge: requestChallengeMutation.isPending || autoVerifyLoading,
    isVerifying: verifySignatureMutation.isPending || autoVerifyLoading,

    // Result states
    verificationError:
      autoVerifyError ||
      getErrorMessage(requestChallengeMutation.error) ||
      getErrorMessage(verifySignatureMutation.error),
    verificationSuccess: verifySignatureMutation.isSuccess || autoVerifySuccess,

    // Actions
    requestChallenge,
    proceedToScanSignature,
    goBackVerificationStep,
    verifySignature,
    autoVerify,
    reset,
  };
}
