import { useState, useCallback, useEffect } from 'react';
import { Alert } from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getWallets,
  prepareTransfer,
  prepareBitcoinTransfer,
  broadcastTransfer,
  getWalletHoldings,
} from '@ledova/shared-services';
import {
  CACHE_TIMING,
  getBlockchainDisplayName,
  getChainShortCode,
  getEstimatedFee,
  isBitcoinChain,
  isEthereumChain,
  WALLET_VERIFICATION_STATUS,
} from '@ledova/shared-constants';
import { getErrorMessage } from '@ledova/shared-utils';
import { apiClient } from '../../services/apiClient';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { useMockData } from '../../_mock/useMockData';
import { generateMockTransferableAssets, generateMockTransactionData, generateMockTxHash } from './_mock/mock';
import { generateMockWalletsData } from '../wallets/_mock/mock';
import type {
  Wallet,
  PrepareTransferRequest,
  PrepareBitcoinTransferRequest,
  BroadcastTransferRequest,
  TransferState,
  TransactionData,
  TransferableAsset,
  WalletHolding,
} from '@ledova/shared-types';

const INITIAL_STATE: TransferState = {
  step: 'select-wallet',
  wallet: null,
  selectedAsset: null,
  toAddress: '',
  amount: '',
  transactionData: null,
  signedTransaction: '',
  txHash: '',
};

function buildTransferableAssets(wallet: Wallet, holdings: WalletHolding[]): TransferableAsset[] {
  const chain = wallet.chain;
  const chainShortCode = getChainShortCode(chain);
  const assets: TransferableAsset[] = [];

  const nativeBalance = parseFloat(wallet.nativeBalance) || 0;
  if (nativeBalance > 0) {
    assets.push({
      uuid: `native-${wallet.uuid}`,
      symbol: chainShortCode,
      name: getBlockchainDisplayName(chainShortCode),
      balance: wallet.nativeBalance,
      marketValue: wallet.nativeMarketValue,
      isNative: true,
      decimals: isBitcoinChain(chainShortCode) ? 8 : 18,
      chain,
    });
  }

  if (isEthereumChain(chainShortCode)) {
    for (const holding of holdings) {
      const balance = parseFloat(holding.quantity) || 0;
      if (balance > 0 && holding.asset?.contractAddress) {
        assets.push({
          uuid: holding.uuid,
          symbol: holding.assetSymbol,
          name: holding.assetName,
          balance: holding.quantity,
          marketValue: holding.marketValue,
          isNative: false,
          contractAddress: holding.asset.contractAddress,
          decimals: holding.asset.decimals || 18,
          chain,
        });
      }
    }
  }

  return assets;
}

export function useTransfers() {
  const USE_MOCK_DATA = useMockData();
  const queryClient = useQueryClient();
  const { selectedAccount } = useUserPreferences();
  const [state, setState] = useState<TransferState>(INITIAL_STATE);
  const [pendingBroadcast, setPendingBroadcast] = useState(false);
  const [transferableAssets, setTransferableAssets] = useState<TransferableAsset[]>([]);

  const walletsQuery = useQuery({
    queryKey: ['wallets', selectedAccount?.uuid, { order_by: 'name' }],
    queryFn: () => getWallets(apiClient, { user_account: selectedAccount!.uuid, order_by: 'name' }),
    enabled: !USE_MOCK_DATA && !!selectedAccount?.uuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const holdingsQuery = useQuery({
    queryKey: ['wallet-holdings', state.wallet?.uuid],
    queryFn: () => getWalletHoldings(apiClient, state.wallet!.uuid),
    enabled: !USE_MOCK_DATA && !!state.wallet?.uuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });

  useEffect(() => {
    if (USE_MOCK_DATA && state.wallet) {
      const assets = generateMockTransferableAssets(state.wallet);
      setTransferableAssets(assets);
      if (assets.length > 0) {
        setState((prev) => ({ ...prev, selectedAsset: assets[0] }));
      }
    } else if (state.wallet && holdingsQuery.data?.data) {
      const holdings = holdingsQuery.data.data.results || holdingsQuery.data.data || [];
      const assets = buildTransferableAssets(state.wallet, holdings as WalletHolding[]);
      setTransferableAssets(assets);
      if (assets.length > 0) {
        setState((prev) => ({ ...prev, selectedAsset: assets[0] }));
      }
    } else if (state.wallet) {
      const chainShortCode = getChainShortCode(state.wallet.chain);
      const nativeAsset: TransferableAsset = {
        uuid: `native-${state.wallet.uuid}`,
        symbol: chainShortCode,
        name: getBlockchainDisplayName(chainShortCode),
        balance: state.wallet.nativeBalance,
        marketValue: state.wallet.nativeMarketValue,
        isNative: true,
        decimals: isBitcoinChain(chainShortCode) ? 8 : 18,
        chain: state.wallet.chain,
      };
      setTransferableAssets([nativeAsset]);
      setState((prev) => ({ ...prev, selectedAsset: nativeAsset }));
    }
  }, [state.wallet, holdingsQuery.data, USE_MOCK_DATA]);

  const prepareTransferMutation = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: PrepareTransferRequest | PrepareBitcoinTransferRequest }) =>
      'amountBtc' in data ? prepareBitcoinTransfer(apiClient, uuid, data) : prepareTransfer(apiClient, uuid, data),
    onSuccess: (response) => {
      setState((prev) => ({
        ...prev,
        step: 'review',
        transactionData: response.data as unknown as TransactionData,
      }));
    },
  });

  const broadcastTransferMutation = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: BroadcastTransferRequest }) =>
      broadcastTransfer(apiClient, uuid, data),
    onSuccess: (response) => {
      setState((prev) => ({
        ...prev,
        step: 'success',
        txHash: response.data.txHash || '',
      }));
      queryClient.invalidateQueries({ queryKey: ['wallets'] });
    },
  });

  useEffect(() => {
    if (pendingBroadcast && state.signedTransaction && state.wallet && state.step === 'broadcast') {
      setPendingBroadcast(false);

      if (USE_MOCK_DATA) {
        const mockTxHash = generateMockTxHash(state.wallet.chain);

        setState((prev) => ({
          ...prev,
          step: 'success',
          txHash: mockTxHash,
        }));
        return;
      }

      const chain = getChainShortCode(state.wallet.chain);
      const fee = isBitcoinChain(chain) ? state.transactionData?.feeBtc : state.transactionData?.gasCostEth;

      broadcastTransferMutation.mutate({
        uuid: state.wallet.uuid,
        data: {
          signedTransaction: state.signedTransaction,
          toAddress: state.toAddress,
          amount: state.amount,
          transactionFee: fee,
          tokenContract: state.selectedAsset?.isNative ? undefined : state.selectedAsset?.contractAddress,
        },
      });
    }
  }, [pendingBroadcast, state.signedTransaction, state.wallet, state.step, broadcastTransferMutation, USE_MOCK_DATA]);

  const selectWallet = useCallback((wallet: Wallet) => {
    setState((prev) => ({ ...prev, step: 'enter-details', wallet, selectedAsset: null, amount: '' }));
    setTransferableAssets([]);
  }, []);

  const selectAsset = useCallback((asset: TransferableAsset) => {
    setState((prev) => ({ ...prev, selectedAsset: asset, amount: '' }));
  }, []);

  const setToAddress = useCallback((toAddress: string) => {
    setState((prev) => ({ ...prev, toAddress }));
  }, []);

  const setAmount = useCallback((amount: string) => {
    setState((prev) => ({ ...prev, amount }));
  }, []);

  const useMaxAmount = useCallback(() => {
    if (!state.wallet || !state.selectedAsset) return;

    const balance = parseFloat(state.selectedAsset.balance);
    if (isNaN(balance) || balance <= 0) return;

    const chain = getChainShortCode(state.wallet.chain);
    const symbol = state.selectedAsset.symbol;

    if (state.selectedAsset.isNative) {
      const estimatedFee = getEstimatedFee(chain);
      const maxAmount = balance - estimatedFee;

      if (maxAmount <= 0) {
        Alert.alert(
          'Low Balance Warning',
          `Your balance (${balance.toFixed(8)} ${symbol}) is very low. After estimated gas fees (~${estimatedFee} ${chain}), there may not be enough to transfer. The transaction may fail.`,
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Try Anyway',
              onPress: () => {
                const safeAmount = balance * 0.9;
                const finalAmount = parseFloat(safeAmount.toFixed(8)).toString();
                setState((prev) => ({ ...prev, amount: finalAmount }));
              },
            },
          ],
        );
        return;
      }

      const finalAmount = parseFloat(maxAmount.toFixed(8)).toString();
      setState((prev) => ({ ...prev, amount: finalAmount }));
    } else {
      const decimals = Math.min(state.selectedAsset.decimals, 8);
      const finalAmount = parseFloat(balance.toFixed(decimals)).toString();
      setState((prev) => ({ ...prev, amount: finalAmount }));
    }
  }, [state.wallet, state.selectedAsset]);

  const submitTransfer = useCallback(() => {
    if (!state.wallet || !state.selectedAsset) return;

    if (USE_MOCK_DATA) {
      const mockTransactionData = generateMockTransactionData(
        state.wallet,
        state.toAddress,
        state.amount,
        state.selectedAsset.isNative,
      );

      setState((prev) => ({
        ...prev,
        step: 'review',
        transactionData: mockTransactionData,
      }));
      return;
    }

    const chain = getChainShortCode(state.wallet.chain);
    let data: PrepareTransferRequest | PrepareBitcoinTransferRequest;

    if (state.selectedAsset.isNative) {
      data = isBitcoinChain(chain)
        ? { toAddress: state.toAddress, amountBtc: state.amount }
        : { toAddress: state.toAddress, amountEth: state.amount };
    } else {
      data = {
        toAddress: state.toAddress,
        amountToken: state.amount,
        tokenContract: state.selectedAsset.contractAddress,
      };
    }

    prepareTransferMutation.mutate({
      uuid: state.wallet.uuid,
      data,
    });
  }, [state.wallet, state.selectedAsset, state.toAddress, state.amount, prepareTransferMutation, USE_MOCK_DATA]);

  const proceedToSign = useCallback(() => {
    setState((prev) => ({ ...prev, step: 'sign' }));
  }, []);

  const handleSignature = useCallback((signedTransaction: string) => {
    setPendingBroadcast(true);
    setState((prev) => ({ ...prev, step: 'broadcast', signedTransaction }));
  }, []);

  const backToReview = useCallback(() => {
    setState((prev) => ({ ...prev, step: 'review', signedTransaction: '' }));
  }, []);

  const cancel = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
    setPendingBroadcast(false);
  }, []);

  const allWallets = USE_MOCK_DATA ? generateMockWalletsData() : walletsQuery.data?.data.results || [];
  const wallets = allWallets.filter((w: Wallet) => w.verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED);

  return {
    step: state.step,
    wallet: state.wallet,
    selectedAsset: state.selectedAsset,
    transferableAssets,
    toAddress: state.toAddress,
    amount: state.amount,
    transactionData: state.transactionData,
    txHash: state.txHash,
    wallets,
    isLoading: USE_MOCK_DATA ? false : walletsQuery.isLoading,
    isLoadingHoldings: USE_MOCK_DATA ? false : holdingsQuery.isLoading,
    isPreparing: USE_MOCK_DATA ? false : prepareTransferMutation.isPending,
    isBroadcasting: USE_MOCK_DATA ? false : broadcastTransferMutation.isPending,
    prepareError: USE_MOCK_DATA ? null : getErrorMessage(prepareTransferMutation.error),
    broadcastError: USE_MOCK_DATA ? null : getErrorMessage(broadcastTransferMutation.error),
    selectWallet,
    selectAsset,
    setToAddress,
    setAmount,
    useMaxAmount,
    submitTransfer,
    proceedToSign,
    handleSignature,
    backToReview,
    cancel,
    reset,
  };
}
