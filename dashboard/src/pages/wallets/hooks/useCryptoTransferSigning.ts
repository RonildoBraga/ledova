import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { prepareTransfer, prepareBitcoinTransfer, broadcastTransfer } from '@ledova/shared-services';
import { BLOCKCHAIN } from '@ledova/shared-constants';
import apiClient from '@services/apiClient';
import type { Wallet, PreparedWalletTransfer } from '@ledova/shared-types';

interface UseCryptoTransferSigningParams {
  wallet: Wallet | null;
  toAddress: string;
  amount: string;
  tokenContract?: string;
}

interface UseCryptoTransferSigningResult {
  preparedTransaction: PreparedWalletTransfer | null;
  isPreparing: boolean;
  isBroadcasting: boolean;
  prepareError: string | null;
  broadcastError: string | null;
  prepare: () => void;
  broadcast: (signedTx: string) => Promise<string>;
  reset: () => void;
}

export function useCryptoTransferSigning({
  wallet,
  toAddress,
  amount,
  tokenContract,
}: UseCryptoTransferSigningParams): UseCryptoTransferSigningResult {
  const queryClient = useQueryClient();
  const [preparedTransaction, setPreparedTransaction] = useState<PreparedWalletTransfer | null>(null);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [broadcastError, setBroadcastError] = useState<string | null>(null);

  const prepareMutation = useMutation({
    mutationFn: async (): Promise<PreparedWalletTransfer> => {
      if (!wallet) throw new Error('No wallet selected');
      if (wallet.chain === BLOCKCHAIN.BITCOIN) {
        const response = await prepareBitcoinTransfer(apiClient, wallet.uuid, { toAddress, amountBtc: amount });
        return response.data;
      }
      const data = tokenContract ? { toAddress, amountToken: amount, tokenContract } : { toAddress, amountEth: amount };
      const response = await prepareTransfer(apiClient, wallet.uuid, data);
      return response.data;
    },
    onSuccess: (data) => {
      setPreparedTransaction(data);
      setPrepareError(null);
    },
    onError: (err) => {
      const message = getErrorMessage(err);
      setPrepareError(message);
      setPreparedTransaction(null);
    },
  });

  const broadcastMutation = useMutation({
    mutationFn: async (signedTx: string) => {
      if (!wallet) throw new Error('No wallet selected');
      const response = await broadcastTransfer(apiClient, wallet.uuid, {
        signedTransaction: signedTx,
      });
      return response.data;
    },
    onSuccess: () => {
      setBroadcastError(null);
      queryClient.invalidateQueries({ queryKey: ['wallets'] });
    },
    onError: (err) => {
      const message = getErrorMessage(err);
      setBroadcastError(message);
    },
  });

  const prepare = useCallback(() => {
    setPrepareError(null);
    prepareMutation.mutate();
  }, [prepareMutation]);

  const broadcast = useCallback(
    async (signedTx: string): Promise<string> => {
      const result = await broadcastMutation.mutateAsync(signedTx);
      return result.txHash || '';
    },
    [broadcastMutation],
  );

  const reset = useCallback(() => {
    setPreparedTransaction(null);
    setPrepareError(null);
    setBroadcastError(null);
  }, []);

  return {
    preparedTransaction,
    isPreparing: prepareMutation.isPending,
    isBroadcasting: broadcastMutation.isPending,
    prepareError,
    broadcastError,
    prepare,
    broadcast,
    reset,
  };
}

function getErrorMessage(error: unknown): string {
  if (!error) return 'An unknown error occurred';
  if (typeof error === 'string') return error;

  const axiosError = error as {
    response?: { data?: { detail?: string; message?: string }; status?: number };
    message?: string;
  };

  if (axiosError.response?.data?.detail) return axiosError.response.data.detail;
  if (axiosError.response?.data?.message) return axiosError.response.data.message;
  if (axiosError.message) return axiosError.message;

  return 'An error occurred while processing your request';
}
