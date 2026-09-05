import { useState, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { SwapTypedData, Wallet } from '@ledova/shared';
import { encodeEthereumTypedData, encodeEthereumTransaction } from '../../utils/keystone/urEncoder';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import { signEthereumTransaction, signEthereumTypedData } from '../../utils/softwareWallet/localSigner';
import {
  useOrderSwapData,
  useSubmitOrderSwapSignature,
  useOrderSwapApprovalStatus,
  useOrderSwapApprovalData,
  useBroadcastTransaction,
} from './useAtomicSwaps';

export type SwapSigningStep =
  | 'instructions'
  | 'show-approval-qr'
  | 'signing-approval-software'
  | 'scan-approval-signature'
  | 'broadcasting-approval'
  | 'show-swap-qr'
  | 'signing-swap-software'
  | 'scan-signature'
  | 'submitting'
  | 'success'
  | 'error';

interface UseAtomicSwapSigningProps {
  orderUuid: string | undefined;
  walletAddress: string;
  wallet: Wallet | null;
}

export function useAtomicSwapSigning({ orderUuid, walletAddress, wallet }: UseAtomicSwapSigningProps) {
  const queryClient = useQueryClient();

  const [signingStep, setSigningStep] = useState<SwapSigningStep>('instructions');
  const [swapQrCborHex, setSwapQrCborHex] = useState<string | null>(null);
  const [swapQrType, setSwapQrType] = useState<string | null>(null);
  const [signingError, setSigningError] = useState<string | null>(null);
  const [approvalQrCborHex, setApprovalQrCborHex] = useState<string | null>(null);
  const [approvalQrType, setApprovalQrType] = useState<string | null>(null);

  const { data: swapData, isLoading: isLoadingSwapData, error: loadError } = useOrderSwapData(orderUuid, walletAddress);
  const { data: approvalStatus, refetch: refetchApprovalStatus } = useOrderSwapApprovalStatus(orderUuid, walletAddress);
  const { data: approvalData, isLoading: isLoadingApprovalData } = useOrderSwapApprovalData(orderUuid, walletAddress);

  const submitSignature = useSubmitOrderSwapSignature();
  const broadcastTransaction = useBroadcastTransaction();

  const needsApproval = approvalStatus?.needsApproval ?? null;
  const approvalTokenSymbol = approvalStatus?.tokenSymbol ?? approvalData?.tokenSymbol ?? null;
  const isSoftwareWallet = wallet?.walletType === 'software';

  const handleSignatureScanned = useCallback(
    async (signature: string) => {
      if (!orderUuid) {
        setSigningError('Order UUID not available');
        return;
      }

      setSigningStep('submitting');
      setSigningError(null);

      try {
        await submitSignature.mutateAsync({
          orderUuid,
          data: {
            signature,
            signerAddress: walletAddress,
          },
        });
        setSigningStep('success');
        queryClient.invalidateQueries({ queryKey: ['trading', 'orders'] });
        queryClient.invalidateQueries({ queryKey: ['trading', 'allOpenOrders'] });
        queryClient.invalidateQueries({ queryKey: ['trading', 'swaps'] });
      } catch (err) {
        setSigningError((err as Error).message || 'Failed to submit signature');
        setSigningStep('error');
      }
    },
    [orderUuid, walletAddress, submitSignature, queryClient],
  );

  const handleSoftwareSwapSigning = useCallback(async () => {
    if (!swapData || !wallet?.derivationPath || !wallet?.masterFingerprint) {
      setSigningError('Missing data for swap signing');
      setSigningStep('error');
      return;
    }

    setSigningStep('signing-swap-software');
    setSigningError(null);

    try {
      const mnemonic = await getSeedPhrase(wallet.masterFingerprint);
      if (!mnemonic) {
        setSigningStep('instructions');
        return;
      }

      const typedData = swapData.typedData as SwapTypedData;
      const { EIP712Domain: _EIP712Domain, ...signingTypes } = typedData.types;
      const signature = await signEthereumTypedData(
        mnemonic,
        wallet.derivationPath,
        typedData.domain,
        signingTypes,
        typedData.message as unknown as Record<string, unknown>,
      );

      handleSignatureScanned(signature);
    } catch (err) {
      setSigningError(err instanceof Error ? err.message : 'Failed to sign swap');
      setSigningStep('error');
    }
  }, [swapData, wallet, handleSignatureScanned]);

  const proceedToSwapSigning = useCallback(() => {
    if (!swapData || !wallet?.derivationPath || !wallet?.masterFingerprint) {
      setSigningError('Missing data for swap signing');
      setSigningStep('error');
      return;
    }

    if (isSoftwareWallet) {
      handleSoftwareSwapSigning();
      return;
    }

    const qrData = encodeEthereumTypedData(
      walletAddress,
      swapData.typedData,
      wallet.derivationPath,
      wallet.masterFingerprint,
      Number(swapData.typedData.domain.chainId),
    );

    if (qrData) {
      setSwapQrCborHex(qrData.cborHex);
      setSwapQrType(qrData.type);
      setSigningStep('show-swap-qr');
    } else {
      setSigningError('Failed to generate QR code for signing.');
      setSigningStep('error');
    }
  }, [swapData, wallet, walletAddress, isSoftwareWallet, handleSoftwareSwapSigning]);

  const handleApprovalSignatureScanned = useCallback(
    async (signedTx: string) => {
      setSigningStep('broadcasting-approval');
      setSigningError(null);

      try {
        await broadcastTransaction.mutateAsync(signedTx);
        await refetchApprovalStatus();
        await new Promise((resolve) => setTimeout(resolve, 2000));
        proceedToSwapSigning();
      } catch (err) {
        setSigningError((err as Error).message || 'Failed to broadcast approval transaction');
        setSigningStep('error');
      }
    },
    [broadcastTransaction, refetchApprovalStatus, proceedToSwapSigning],
  );

  const handleSoftwareApprovalSigning = useCallback(async () => {
    if (!approvalData?.transaction || !wallet?.derivationPath || !wallet?.masterFingerprint) {
      setSigningError('Missing approval data or wallet');
      setSigningStep('error');
      return;
    }

    setSigningStep('signing-approval-software');
    setSigningError(null);

    try {
      const mnemonic = await getSeedPhrase(wallet.masterFingerprint);
      if (!mnemonic) {
        setSigningStep('instructions');
        return;
      }

      const tx = approvalData.transaction;
      const unsignedTx = {
        to: tx.to,
        value: BigInt(tx.value),
        gasLimit: BigInt(tx.gas),
        gasPrice: BigInt(tx.gasPrice),
        nonce: parseInt(tx.nonce, 16),
        data: tx.data,
        chainId: parseInt(tx.chainId, 16),
        type: 0,
      };

      const signedTx = await signEthereumTransaction(mnemonic, wallet.derivationPath, unsignedTx);
      await handleApprovalSignatureScanned(signedTx);
    } catch (err) {
      setSigningError(err instanceof Error ? err.message : 'Failed to sign approval');
      setSigningStep('error');
    }
  }, [approvalData, wallet, handleApprovalSignatureScanned]);

  const startSigning = useCallback(() => {
    setSigningError(null);
    setSwapQrCborHex(null);
    setSwapQrType(null);
    setApprovalQrCborHex(null);
    setApprovalQrType(null);

    if (loadError) {
      setSigningError((loadError as Error).message || 'Failed to load swap data');
      setSigningStep('error');
      return;
    }

    if (!swapData) {
      setSigningError('Swap data not available');
      setSigningStep('error');
      return;
    }

    if (needsApproval === true && approvalData?.needsApproval && approvalData.transaction) {
      if (isSoftwareWallet) {
        handleSoftwareApprovalSigning();
        return;
      }

      if (!wallet?.derivationPath || !wallet?.masterFingerprint) {
        setSigningError('Missing hardware wallet data (derivation path or master fingerprint).');
        setSigningStep('error');
        return;
      }

      const tx = approvalData.transaction;
      const approvalQr = encodeEthereumTransaction(
        walletAddress,
        {
          nonce: parseInt(tx.nonce, 16),
          to: tx.to,
          value: parseInt(tx.value, 16),
          gas: parseInt(tx.gas, 16),
          chainId: parseInt(tx.chainId, 16),
          gasPrice: parseInt(tx.gasPrice, 16),
          data: tx.data,
        },
        wallet.derivationPath,
        wallet.masterFingerprint,
      );

      if (approvalQr) {
        setApprovalQrCborHex(approvalQr.cbor.toString('hex'));
        setApprovalQrType(approvalQr.type);
        setSigningStep('show-approval-qr');
      } else {
        setSigningError('Failed to generate approval QR code.');
        setSigningStep('error');
      }
      return;
    }

    proceedToSwapSigning();
  }, [
    swapData,
    loadError,
    wallet,
    walletAddress,
    needsApproval,
    approvalData,
    isSoftwareWallet,
    proceedToSwapSigning,
    handleSoftwareApprovalSigning,
  ]);

  const proceedToScanApprovalSignature = useCallback(() => {
    setSigningStep('scan-approval-signature');
    setSigningError(null);
  }, []);

  const proceedToScanSignature = useCallback(() => {
    setSigningStep('scan-signature');
    setSigningError(null);
  }, []);

  const goBack = useCallback(() => {
    if (signingStep === 'scan-signature') {
      setSigningStep('show-swap-qr');
    } else if (signingStep === 'show-swap-qr') {
      setSigningStep('instructions');
    } else if (signingStep === 'scan-approval-signature') {
      setSigningStep('show-approval-qr');
    } else if (signingStep === 'show-approval-qr') {
      setSigningStep('instructions');
    } else if (signingStep === 'error') {
      setSigningStep('instructions');
    }
    setSigningError(null);
  }, [signingStep]);

  const reset = useCallback(() => {
    setSigningStep('instructions');
    setSwapQrCborHex(null);
    setSwapQrType(null);
    setApprovalQrCborHex(null);
    setApprovalQrType(null);
    setSigningError(null);
  }, []);

  return {
    signingStep,
    swapData: swapData || null,
    swapQrCborHex,
    swapQrType,
    signingError,
    needsApproval,
    approvalTokenSymbol,
    approvalQrCborHex,
    approvalQrType,
    isLoadingSwapData,
    isLoadingApprovalData,
    isReady: !isLoadingSwapData && !isLoadingApprovalData && !!swapData && approvalData !== undefined,
    isSubmitting: submitSignature.isPending,
    isBroadcastingApproval: broadcastTransaction.isPending,
    isSoftwareWallet,
    startSigning,
    proceedToScanApprovalSignature,
    handleApprovalSignatureScanned,
    proceedToScanSignature,
    handleSignatureScanned,
    goBack,
    reset,
  };
}
