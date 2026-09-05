import { useState, useCallback } from 'react';
import type {
  CreateOrderRequest,
  CreateOrderMessageResponse,
  CancelOrderMessageResponse,
  TransferOrder,
  Wallet,
} from '@ledova/shared';
import { encodeEthereumMessage } from '../../utils/keystone/urEncoder';
import { getWalletVerificationEvmChainId } from '@ledova/shared';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import { signEthereumMessage } from '../../utils/softwareWallet/localSigner';
import { useOrderCreateMessage, useOrderCancelMessage, useCreateOrder, useCancelOrder } from './useTrading';

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
  orderData?: CreateOrderRequest;
  orderUuid?: string;
  wallet: Wallet | null;
  onSuccess?: (order: TransferOrder) => void;
}

export function useOrderSigning({ mode, orderData, orderUuid, wallet, onSuccess }: UseOrderSigningProps) {
  const [step, setStep] = useState<OrderSigningStep>('idle');
  const [messageData, setMessageData] = useState<CreateOrderMessageResponse | CancelOrderMessageResponse | null>(null);
  const [qrData, setQrData] = useState<{ cborHex: string; type: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createMessageMutation = useOrderCreateMessage();
  const cancelMessageMutation = useOrderCancelMessage();
  const createOrderMutation = useCreateOrder();
  const cancelOrderMutation = useCancelOrder();

  const isCreating = mode === 'create';
  const isSoftwareWallet = wallet?.walletType === 'software';

  const start = useCallback(() => {
    setStep('getting-message');
    setMessageData(null);
    setQrData(null);
    setError(null);

    if (isCreating && orderData) {
      createMessageMutation.mutate(orderData, {
        onSuccess: (data) => {
          setMessageData(data);
          setStep('instructions');
        },
        onError: (err) => {
          setError(err instanceof Error ? err.message : 'Failed to get signing message');
          setStep('error');
        },
      });
    } else if (!isCreating && orderUuid) {
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
  }, [isCreating, orderData, orderUuid, createMessageMutation, cancelMessageMutation]);

  const generateQrCode = useCallback(() => {
    if (!messageData || !wallet) {
      setError('Missing message data or wallet');
      setStep('error');
      return;
    }

    const encoded = encodeEthereumMessage(
      wallet.address,
      messageData.message,
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

      if (isCreating && orderData) {
        createOrderMutation.mutate(
          {
            ...orderData,
            message: messageData.message,
            signature,
          },
          {
            onSuccess: (order) => {
              setStep('success');
              onSuccess?.(order);
            },
            onError: (err) => {
              setError(err instanceof Error ? err.message : 'Failed to create order');
              setStep('error');
            },
          },
        );
      } else if (!isCreating && orderUuid) {
        cancelOrderMutation.mutate(
          {
            uuid: orderUuid,
            message: messageData.message,
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
    [messageData, isCreating, orderData, orderUuid, createOrderMutation, cancelOrderMutation, onSuccess],
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
        return; // User cancelled biometric
      }

      const signature = await signEthereumMessage(mnemonic, wallet.derivationPath, messageData.message);
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
    isSubmitting: createOrderMutation.isPending || cancelOrderMutation.isPending,
    start,
    proceedToSign,
    handleSignatureReceived,
    proceedToScanSignature: () => setStep('scan-signature'),
    goBack,
    reset,
  };
}
