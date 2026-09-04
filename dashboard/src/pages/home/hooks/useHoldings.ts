import { useMemo } from 'react';
import { useQueries } from '@tanstack/react-query';
import { getWalletHoldings } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import type { Wallet, HoldingWithWallet } from '@ledova/shared-types';
import { calculateHoldingsSummary, calculateAssetAllocation } from '@ledova/shared-utils';
import apiClient from '@services/apiClient';

export function useHoldings(walletsList: Wallet[]) {
  const holdingsQueries = useQueries({
    queries: walletsList.map((wallet) => ({
      queryKey: ['walletHoldings', wallet.uuid],
      queryFn: () => getWalletHoldings(apiClient, wallet.uuid),
      enabled: !!wallet.uuid,
      staleTime: CACHE_TIMING.SHORT_STALE_TIME,
      gcTime: CACHE_TIMING.MEDIUM_GC_TIME,
    })),
  });

  const holdings: HoldingWithWallet[] = useMemo(
    () =>
      holdingsQueries.flatMap((query, index) => {
        const responseData = query.data?.data;
        const holdingsData = Array.isArray(responseData) ? responseData : responseData?.results || [];
        const wallet = walletsList[index];
        return holdingsData.map((holding) => ({
          ...holding,
          walletInfo: {
            uuid: wallet?.uuid || '',
            name: wallet?.name,
            address: wallet?.address || '',
            chain: wallet?.chain || '',
          },
        }));
      }),
    [holdingsQueries, walletsList],
  );

  const summary = useMemo(() => calculateHoldingsSummary(holdings, walletsList.length), [holdings, walletsList.length]);

  const assetAllocation = useMemo(
    () => calculateAssetAllocation(holdings, summary.totalValue),
    [holdings, summary.totalValue],
  );

  const assetQuantities = useMemo(() => {
    const quantities: Record<string, number> = {};
    holdings.forEach((holding) => {
      const symbol = holding.assetSymbol || holding.asset?.symbol;
      if (symbol) {
        const currentQuantity = quantities[symbol] || 0;
        quantities[symbol] = currentQuantity + parseFloat(holding.quantity || '0');
      }
    });
    return quantities;
  }, [holdings]);

  return {
    summary,
    assetAllocation,
    assetQuantities,
    isLoading: holdingsQueries.some((q) => q.isLoading),
    hasError: holdingsQueries.some((q) => q.error),
  };
}
