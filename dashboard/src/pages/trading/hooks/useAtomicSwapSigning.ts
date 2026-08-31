import { useState, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { SwapOrder, SwapTypedData, Wallet } from '@ledova/shared-types';
import { encodeEthereumTypedData, encodeEthereumTransaction } from '@utils/keystone/urEncoder';
import { signEthereumTypedData, signEthereumTransaction, deriveAddress } from '@utils/softwareWallet/localSigner';
import {
  useOrderSwapData,
  useSubmitOrderSwapSignature,
  useOrderSwapApprovalStatus,
  useOrderSwapApprovalData,
  useBroadcastTransaction,
} from './useAtomicSwaps';

export type SwapSigningStep =
  | 'instructions'
  | 'checking-approval'
  | 'show-approval-qr'
  | 'scan-approval-signature'
  | 'signing-approval-software'
  | 'broadcasting-approval'
  | 'show-swap-qr'
  | 'scan-signature'
  | 'signing-swap-software'
  | 'submitting'
  | 'success'
  | 'error';

interface SwapSigningData {
  swapOrder: SwapOrder;
  typedData: SwapTypedData;
  userRole: string;
  hasSigned: boolean;
}

interface UseAtomicSwapSigningProps {
  orderUuid: string | undefined;
  walletAddress: string;
  wallet: Wallet | null;
}

interface UseAtomicSwapSigningReturn {
  signingStep: SwapSigningStep;
  swapData: SwapSigningData | null;
  swapQrCborHex: string | null;
  swapQrType: string | null;
  signingError: string | null;
  signingSuccess: boolean;
  needsApproval: boolean | null;
  approvalTokenSymbol: string | null;
  approvalQrCborHex: string | null;
  approvalQrType: string | null;
  unsignedApprovalTx: {
    to: string;
    value: string;
    gas: string;
    gasPrice: string;
    nonce: string;
    data: string;
    chainId: string;
  } | null;
  isLoadingSwapData: boolean;
  isLoadingApprovalData: boolean;
  isReady: boolean;
  isSubmitting: boolean;
  isBroadcastingApproval: boolean;
  isSoftwareWallet: boolean;
  seedPhrase: string;
  setSeedPhrase: (value: string) => void;
  startSigning: () => void;
  proceedToScanApprovalSignature: () => void;
  handleApprovalSignatureScanned: (signedTx: string) => Promise<void>;
  handleSoftwareApprovalSign: () => Promise<void>;
  handleSoftwareSwapSign: () => Promise<void>;
  proceedToScanSignature: () => void;
  handleSignatureScanned: (signature: string) => Promise<void>;
  goBack: () => void;
  reset: () => void;
}

interface UnsignedTransaction {
  to: string;
  value: string;
  gas: string;
  gasPrice: string;
  nonce: string;
  data: string;
  chainId: string;
}

export function useAtomicSwapSigning({
  orderUuid,
  walletAddress,
  wallet,
}: UseAtomicSwapSigningProps): UseAtomicSwapSigningReturn {
  const queryClient = useQueryClient();

  const [signingStep, setSigningStep] = useState<SwapSigningStep>('instructions');
  const [swapQrCborHex, setSwapQrCborHex] = useState<string | null>(null);
  const [swapQrType, setSwapQrType] = useState<string | null>(null);
  const [signingError, setSigningError] = useState<string | null>(null);
  const [signingSuccess, setSigningSuccess] = useState(false);
  const [approvalQrCborHex, setApprovalQrCborHex] = useState<string | null>(null);
  const [approvalQrType, setApprovalQrType] = useState<string | null>(null);
  const [unsignedApprovalTx, setUnsignedApprovalTx] = useState<UnsignedTransaction | null>(null);
  const [seedPhrase, setSeedPhrase] = useState('');

  const isSoftwareWallet = wallet?.walletType === 'software' || (!wallet?.derivationPath && !wallet?.masterFingerprint);

  const { data: swapData, isLoading: isLoadingSwapData, error: loadError } = useOrderSwapData(orderUuid, walletAddress);

  const { data: approvalStatus, refetch: refetchApprovalStatus } = useOrderSwapApprovalStatus(orderUuid, walletAddress);
  const { data: approvalData, isLoading: isLoadingApprovalData } = useOrderSwapApprovalData(orderUuid, walletAddress);

  const submitSignature = useSubmitOrderSwapSignature();
  const broadcastTransaction = useBroadcastTransaction();

  const needsApproval = approvalStatus?.needsApproval ?? null;
  const approvalTokenSymbol = approvalStatus?.tokenSymbol ?? approvalData?.tokenSymbol ?? null;

  const startSigning = useCallback(() => {
    setSigningError(null);
    setSigningSuccess(false);
    setSwapQrCborHex(null);
    setSwapQrType(null);
    setApprovalQrCborHex(null);
    setApprovalQrType(null);
    setUnsignedApprovalTx(null);

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

    if (isSoftwareWallet) {
      if (needsApproval === true && approvalData?.needsApproval && approvalData.transaction) {
        setUnsignedApprovalTx(approvalData.transaction);
        setSigningStep('signing-approval-software');
      } else {
        setSigningStep('signing-swap-software');
      }
      return;
    }

    if (!wallet?.derivationPath || !wallet?.masterFingerprint) {
      setSigningError('Hardware wallet data missing (derivation path or master fingerprint).');
      setSigningStep('error');
      return;
    }

    if (needsApproval === true && approvalData?.needsApproval && approvalData.transaction) {
      const approvalQr = encodeEthereumTransaction(
        approvalData.transaction,
        wallet.derivationPath,
        wallet.masterFingerprint,
      );

      if (approvalQr) {
        setApprovalQrCborHex(approvalQr.cborHex);
        setApprovalQrType(approvalQr.type);
        setUnsignedApprovalTx(approvalData.transaction);
        setSigningStep('show-approval-qr');
      } else {
        setSigningError('Failed to generate approval QR code.');
        setSigningStep('error');
      }
      return;
    }

    proceedToSwapSigning();
  }, [swapData, loadError, wallet, walletAddress, needsApproval, approvalData]);

  const proceedToSwapSigning = useCallback(() => {
    if (!swapData || !wallet?.derivationPath || !wallet?.masterFingerprint) {
      setSigningError('Missing data for swap signing');
      setSigningStep('error');
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
  }, [swapData, wallet, walletAddress]);

  const proceedToScanApprovalSignature = useCallback(() => {
    setSigningStep('scan-approval-signature');
    setSigningError(null);
  }, []);

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

  const proceedToScanSignature = useCallback(() => {
    setSigningStep('scan-signature');
    setSigningError(null);
  }, []);

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
        setSigningSuccess(true);
        setSigningStep('success');
        queryClient.invalidateQueries({ queryKey: ['orders'] });
        queryClient.invalidateQueries({ queryKey: ['open-orders'] });
        queryClient.invalidateQueries({ queryKey: ['swap-data'] });
      } catch (err) {
        setSigningError((err as Error).message || 'Failed to submit signature');
        setSigningStep('error');
      }
    },
    [orderUuid, walletAddress, submitSignature, queryClient],
  );

  const handleSoftwareApprovalSign = useCallback(async () => {
    if (!unsignedApprovalTx || !wallet?.derivationPath || !seedPhrase.trim()) return;

    try {
      const derivedAddr = deriveAddress(seedPhrase.trim(), wallet.derivationPath);
      if (derivedAddr.toLowerCase() !== walletAddress.toLowerCase()) {
        setSigningError('Seed phrase does not match this wallet address');
        return;
      }

      setSigningStep('broadcasting-approval');
      const tx = {
        to: unsignedApprovalTx.to,
        value: unsignedApprovalTx.value,
        gasLimit: unsignedApprovalTx.gas,
        gasPrice: unsignedApprovalTx.gasPrice,
        nonce: parseInt(unsignedApprovalTx.nonce),
        data: unsignedApprovalTx.data,
        chainId: parseInt(unsignedApprovalTx.chainId),
        type: 0,
      };
      const signedTx = await signEthereumTransaction(seedPhrase.trim(), wallet.derivationPath, tx);
      await broadcastTransaction.mutateAsync(signedTx);
      await refetchApprovalStatus();
      await new Promise((resolve) => setTimeout(resolve, 2000));
      setSigningStep('signing-swap-software');
    } catch (err) {
      setSeedPhrase('');
      setSigningError((err as Error).message || 'Failed to sign approval transaction');
      setSigningStep('error');
    }
  }, [unsignedApprovalTx, wallet, walletAddress, seedPhrase, broadcastTransaction, refetchApprovalStatus]);

  const handleSoftwareSwapSign = useCallback(async () => {
    if (!swapData || !wallet?.derivationPath || !seedPhrase.trim()) return;

    try {
      const derivedAddr = deriveAddress(seedPhrase.trim(), wallet.derivationPath);
      if (derivedAddr.toLowerCase() !== walletAddress.toLowerCase()) {
        setSigningError('Seed phrase does not match this wallet address');
        return;
      }

      setSigningStep('submitting');
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { EIP712Domain: _domain, ...signingTypes } = swapData.typedData.types;
      const signature = await signEthereumTypedData(
        seedPhrase.trim(),
        wallet.derivationPath,
        swapData.typedData.domain,
        signingTypes,
        swapData.typedData.message as unknown as Record<string, unknown>,
      );
      setSeedPhrase('');
      await handleSignatureScanned(signature);
    } catch (err) {
      setSeedPhrase('');
      setSigningError((err as Error).message || 'Failed to sign swap');
      setSigningStep('error');
    }
  }, [swapData, wallet, walletAddress, seedPhrase, handleSignatureScanned]);

  const goBack = useCallback(() => {
    if (signingStep === 'scan-signature') {
      setSigningStep('show-swap-qr');
    } else if (signingStep === 'show-swap-qr') {
      setSigningStep('instructions');
    } else if (signingStep === 'scan-approval-signature') {
      setSigningStep('show-approval-qr');
    } else if (
      signingStep === 'show-approval-qr' ||
      signingStep === 'signing-approval-software' ||
      signingStep === 'signing-swap-software'
    ) {
      setSeedPhrase('');
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
    setSigningSuccess(false);
    setSeedPhrase('');
  }, []);

  return {
    signingStep,
    swapData: swapData || null,
    swapQrCborHex,
    swapQrType,
    signingError,
    signingSuccess,
    needsApproval,
    approvalTokenSymbol,
    approvalQrCborHex,
    approvalQrType,
    unsignedApprovalTx,
    isLoadingSwapData,
    isLoadingApprovalData,
    isReady: !isLoadingSwapData && !isLoadingApprovalData && !!swapData && approvalData !== undefined,
    isSubmitting: submitSignature.isPending,
    isBroadcastingApproval: broadcastTransaction.isPending,
    isSoftwareWallet,
    seedPhrase,
    setSeedPhrase,
    startSigning,
    proceedToScanApprovalSignature,
    handleApprovalSignatureScanned,
    handleSoftwareApprovalSign,
    handleSoftwareSwapSign,
    proceedToScanSignature,
    handleSignatureScanned,
    goBack,
    reset,
  };
}
