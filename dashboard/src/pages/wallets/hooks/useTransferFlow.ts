import { useState, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getWhitelistStatus, getWalletHoldings } from '@ledova/shared-services';
import { CACHE_TIMING, BLOCKCHAIN, getChainShortCode, getBlockchainDisplayName } from '@ledova/shared-constants';
import { formatCryptoBalance } from '@ledova/shared-utils';
import apiClient from '@services/apiClient';
import type { Wallet } from '@ledova/shared-types';
import { useCryptoTransferSigning } from './useCryptoTransferSigning';

export type AssetType = 'crypto' | 'stablecoin' | 'share_token';

export interface UnifiedAsset {
  id: string;
  type: AssetType;
  symbol: string;
  name: string;
  balance: string;
  displayBalance: string;
  marketValue: string;
  decimals: number;
  tokenAddress?: string;
}

function mapAssetType(assetType: string): AssetType {
  switch (assetType) {
    case 'tokenized_security':
      return 'share_token';
    case 'stablecoin':
      return 'stablecoin';
    default:
      return 'stablecoin';
  }
}

export function useTransferFlow(selectedWallet: Wallet | null) {
  const [selectedAsset, setSelectedAsset] = useState<UnifiedAsset | null>(null);
  const [toAddress, setToAddress] = useState('');

  const [isSigningModalOpen, setIsSigningModalOpen] = useState(false);
  const [pendingTransfer, setPendingTransfer] = useState<{ toAddress: string; amount: string } | null>(null);

  const isEvmWallet = selectedWallet?.chain === BLOCKCHAIN.ETHEREUM || selectedWallet?.chain === BLOCKCHAIN.BASE;

  const holdingsQuery = useQuery({
    queryKey: ['wallet-holdings', selectedWallet?.uuid],
    queryFn: () => getWalletHoldings(apiClient, selectedWallet!.uuid),
    enabled: !!selectedWallet?.uuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    select: (data) => data.data.results || data.data || [],
  });

  const senderWhitelistQuery = useQuery({
    queryKey: ['whitelistStatus', selectedWallet?.address],
    queryFn: () => getWhitelistStatus(apiClient, selectedWallet!.address),
    enabled: !!selectedWallet?.address && isEvmWallet,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    select: (data) => data.data,
  });

  const isValidEthAddress = toAddress.length === 42 && toAddress.startsWith('0x');
  const recipientWhitelistQuery = useQuery({
    queryKey: ['whitelistStatus', toAddress],
    queryFn: () => getWhitelistStatus(apiClient, toAddress),
    enabled: selectedAsset?.type === 'share_token' && isValidEthAddress,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    select: (data) => data.data,
  });

  const assets = useMemo<UnifiedAsset[]>(() => {
    if (!selectedWallet) return [];

    const assetList: UnifiedAsset[] = [];
    const chainShortCode = getChainShortCode(selectedWallet.chain);

    assetList.push({
      id: `native-${selectedWallet.chain}`,
      type: 'crypto',
      symbol: chainShortCode,
      name: getBlockchainDisplayName(chainShortCode),
      balance: selectedWallet.nativeBalance,
      displayBalance: formatCryptoBalance(selectedWallet.nativeBalance, chainShortCode),
      marketValue: selectedWallet.nativeMarketValue,
      decimals: isEvmWallet ? 18 : 8,
    });

    if (holdingsQuery.data) {
      for (const holding of holdingsQuery.data) {
        const balance = parseFloat(holding.quantity) || 0;
        if (balance > 0 && holding.asset?.contractAddress) {
          const type = mapAssetType(holding.asset.assetType);
          const decimals = holding.asset.decimals || 18;
          const displayDecimals = type === 'share_token' ? 0 : decimals > 6 ? 6 : decimals;
          assetList.push({
            id: holding.uuid,
            type,
            symbol: holding.assetSymbol,
            name: holding.assetName,
            balance: holding.quantity,
            displayBalance: parseFloat(holding.quantity).toFixed(displayDecimals),
            marketValue: holding.marketValue,
            decimals,
            tokenAddress: holding.asset.contractAddress,
          });
        }
      }
    }

    return assetList;
  }, [selectedWallet, isEvmWallet, holdingsQuery.data]);

  const isSenderWhitelisted =
    selectedAsset?.type === 'share_token' ? (senderWhitelistQuery.data?.isWhitelisted ?? false) : true;
  const isRecipientWhitelisted =
    selectedAsset?.type === 'share_token' ? (recipientWhitelistQuery.data?.isWhitelisted ?? false) : true;

  const hasShareTokens = assets.some((a) => a.type === 'share_token');

  const tokenContract = selectedAsset && selectedAsset.type !== 'crypto' ? selectedAsset.tokenAddress : undefined;

  const signing = useCryptoTransferSigning({
    wallet: selectedWallet,
    toAddress: pendingTransfer?.toAddress || '',
    amount: pendingTransfer?.amount || '',
    tokenContract,
  });

  const handleCombinedTransfer = useCallback((asset: UnifiedAsset, toAddr: string, amt: string) => {
    setSelectedAsset(asset);
    setPendingTransfer({ toAddress: toAddr, amount: amt });
    setToAddress(toAddr);
    setIsSigningModalOpen(true);
  }, []);

  const handleCloseSigningModal = useCallback(() => {
    setIsSigningModalOpen(false);
    setPendingTransfer(null);
    signing.reset();
  }, [signing]);

  const handleTransferSuccess = useCallback(() => {
    setSelectedAsset(null);
    setToAddress('');
    setIsSigningModalOpen(false);
    setPendingTransfer(null);
    signing.reset();
  }, [signing]);

  const getTransferType = useCallback((): 'crypto' | 'stablecoin' | 'share_token' => {
    return selectedAsset?.type || 'crypto';
  }, [selectedAsset]);

  return {
    assets,
    selectedAsset,
    hasShareTokens,
    isLoadingAssets: holdingsQuery.isLoading,

    isSenderWhitelisted,
    isRecipientWhitelisted,
    isCheckingRecipientWhitelist: recipientWhitelistQuery.isFetching,
    senderWhitelistStatus: senderWhitelistQuery.data,
    recipientWhitelistStatus: recipientWhitelistQuery.data,

    isSigningModalOpen,

    pendingTransfer,

    signing,

    handleCombinedTransfer,
    handleCloseSigningModal,
    handleTransferSuccess,
    setToAddress,
    getTransferType,
  };
}
