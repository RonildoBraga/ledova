import { useState, useCallback } from 'react';
import type { CreateOrderMessageResponse, CancelOrderMessageResponse, TransferOrder, Wallet } from '@ledova/shared';
import { encodeEthereumTypedData } from '../../utils/keystone/urEncoder';
import { getWalletVerificationEvmChainId } from '@ledova/shared';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import { signEthereumTypedData } from '../../utils/softwareWallet/localSigner';
import { useOrderCancelMessage, useCancelOrder } from './useTrading';

export type OrderSigningStep =
  | 'idle'
  | 'getting-message'
  | 'instructions'
  | 'show-qr'
  | 'signing-software'
  | 'scan-signature'
  | 'submitting'
  | 'success'
  | 'error';

type SigningMode = 'create' | 'cancel';

interface UseOrderSigningProps {
  mode: SigningMode;
  orderUuid?: string;
  wallet: Wallet | null;
  onSuccess?: (order: TransferOrder) => void;
}

export function useOrderSigning({ mode, orderUuid, wallet, onSuccess }: UseOrderSigningProps) {
  const [step, setStep] = useState<OrderSigningStep>('idle');
  const [messageData, setMessageData] = useState<CreateOrderMessageResponse | CancelOrderMessageResponse | null>(null);
  const [qrData, setQrData] = useState<{ cborHex: string; type: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cancelMessageMutation = useOrderCancelMessage();
  const cancelOrderMutation = useCancelOrder();

  const isCreating = mode === 'create';
  const isSoftwareWallet = wallet?.signingPreference === 'software';

  const start = useCallback(() => {
    setStep('getting-message');
    setMessageData(null);
    setQrData(null);
    setError(null);

    if (!isCreating && orderUuid) {
      cancelMessageMutation.mutate(orderUuid, {
        onSuccess: (data) => {
          setMessageData(data);
          setStep('instructions');
        },
        onError: (err) => {
          setError(err instanceof Error ? err.message : 'Failed to get signing message');
          setStep('error');
        },
      });
    }
  }, [isCreating, orderUuid, cancelMessageMutation]);

  const generateQrCode = useCallback(() => {
    if (!messageData || !wallet) {
      setError('Missing message data or wallet');
      setStep('error');
      return;
    }

    const encoded = encodeEthereumTypedData(
      wallet.address,
      { domain: messageData.domain, types: messageData.types, message: messageData.message },
      wallet.derivationPath || undefined,
      wallet.masterFingerprint || undefined,
      getWalletVerificationEvmChainId(wallet.chain) ?? undefined,
    );

    if (!encoded) {
      setError('Failed to encode message for signing');
      setStep('error');
      return;
    }

    setQrData({ cborHex: encoded.cbor.toString('hex'), type: encoded.type });
    setStep('show-qr');
  }, [messageData, wallet]);

  const handleSignatureReceived = useCallback(
    (signature: string) => {
      if (!messageData) return;

      setStep('submitting');

      if (!isCreating && orderUuid) {
        cancelOrderMutation.mutate(
          {
            uuid: orderUuid,
            digest: messageData.digest,
            signature,
          },
          {
            onSuccess: (order) => {
              setStep('success');
              onSuccess?.(order);
            },
            onError: (err) => {
              setError(err instanceof Error ? err.message : 'Failed to cancel order');
              setStep('error');
            },
          },
        );
      }
    },
    [messageData, isCreating, orderUuid, cancelOrderMutation, onSuccess],
  );

  const startSoftwareSigning = useCallback(async () => {
    if (!messageData || !wallet?.derivationPath || !wallet?.masterFingerprint) {
      setError('Missing message data or wallet');
      setStep('error');
      return;
    }

    setStep('signing-software');
    setError(null);

    try {
      const mnemonic = await getSeedPhrase(wallet.masterFingerprint);
      if (!mnemonic) {
        setStep('instructions');
        return;
      }

      const signature = await signEthereumTypedData(
        mnemonic,
        wallet.derivationPath,
        messageData.domain,
        messageData.types,
        messageData.message,
      );
      handleSignatureReceived(signature);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to sign message');
      setStep('error');
    }
  }, [messageData, wallet, handleSignatureReceived]);

  const proceedToSign = useCallback(() => {
    if (isSoftwareWallet) {
      startSoftwareSigning();
    } else {
      generateQrCode();
    }
  }, [isSoftwareWallet, startSoftwareSigning, generateQrCode]);

  const goBack = useCallback(() => {
    if (step === 'scan-signature') {
      setStep('show-qr');
    } else if (step === 'show-qr') {
      setStep('instructions');
    } else if (step === 'error') {
      setStep('instructions');
      setError(null);
    }
  }, [step]);

  const reset = useCallback(() => {
    setStep('idle');
    setMessageData(null);
    setQrData(null);
    setError(null);
  }, []);

  return {
    step,
    messageData,
    qrData,
    error,
    isSoftwareWallet,
    isSubmitting: cancelOrderMutation.isPending,
    start,
    proceedToSign,
    handleSignatureReceived,
    proceedToScanSignature: () => setStep('scan-signature'),
    goBack,
    reset,
  };
}
