import { useQuery, useMutation, useQueryClient, useQueries } from '@tanstack/react-query';
import {
  getShareTokens,
  getUserOrders,
  getOrderCreateMessage,
  getOrderCancelMessage,
  createOrder,
  cancelOrder,
  getWallets,
  getWhitelistStatus,
  getWalletBalances,
  parseTradingError,
  getOrderModificationMessage,
  modifyOrder,
  getOrderBook,
} from '@ledova/shared-services';
import { BLOCKCHAIN, CACHE_TIMING, TRADING_CONFIG, WALLET_VERIFICATION_STATUS } from '@ledova/shared-constants';
import type {
  TransferOrder,
  CreateOrderRequest,
  GetOrdersParams,
  Wallet,
  WhitelistStatus,
  SignedCreateOrderRequest,
  SignedCancelOrderRequest,
  CreateOrderMessageResponse,
  CancelOrderMessageResponse,
  OrderModificationRequest,
  OrderModificationMessageResponse,
  SignedOrderModificationRequest,
} from '@ledova/shared-types';
import apiClient from '@services/apiClient';
import { useSelectedPortfolio } from '@hooks/useSelectedPortfolio';

export { parseTradingError };
export type {
  WhitelistStatus,
  CreateOrderMessageResponse,
  CancelOrderMessageResponse,
  OrderModificationRequest,
  OrderModificationMessageResponse,
  SignedOrderModificationRequest,
};

export const tradingQueryKeys = {
  tokens: ['trading', 'tokens'] as const,
  orders: (params?: GetOrdersParams) => ['trading', 'orders', params] as const,
  order: (uuid: string) => ['trading', 'orders', uuid] as const,
  userOrders: (walletAddress: string) => ['trading', 'userOrders', walletAddress] as const,
  walletBalances: (walletAddress: string) => ['trading', 'walletBalances', walletAddress] as const,
  whitelistStatus: (walletAddress: string) => ['trading', 'whitelistStatus', walletAddress] as const,
  orderModifications: (orderUuid: string) => ['trading', 'orderModifications', orderUuid] as const,
};

export function useUserTradingWallets() {
  const { portfolio, isLoading: isLoadingPortfolio } = useSelectedPortfolio();

  const walletsQuery = useQuery({
    queryKey: ['wallets', portfolio?.userAccount, 'trading'],
    queryFn: () => getWallets(apiClient, { user_account: portfolio!.userAccount }),
    enabled: !!portfolio?.userAccount,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    select: (data) =>
      data.data.results.filter(
        (w: Wallet) =>
          w.verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED &&
          (w.chain === BLOCKCHAIN.ETHEREUM || w.chain === BLOCKCHAIN.BASE),
      ),
  });

  return {
    wallets: walletsQuery.data || ([] as Wallet[]),
    walletAddresses: (walletsQuery.data || []).map((w: Wallet) => w.address),
    isLoading: isLoadingPortfolio || walletsQuery.isLoading,
    error: walletsQuery.error,
    refetch: walletsQuery.refetch,
  };
}

export function useWalletsWhitelistStatus(walletAddresses: string[]) {
  const queries = useQueries({
    queries: walletAddresses.map((address) => ({
      queryKey: tradingQueryKeys.whitelistStatus(address),
      queryFn: () => getWhitelistStatus(apiClient, address).then((res) => res.data),
      enabled: !!address,
      staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
      gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
      retry: false,
    })),
  });

  const isLoading = queries.some((q) => q.isLoading);

  const statusByAddress = new Map<string, WhitelistStatus>();
  queries.forEach((query, index) => {
    if (query.data) {
      statusByAddress.set(walletAddresses[index].toLowerCase(), query.data);
    }
  });

  const isWhitelisted = (address: string): boolean => {
    const status = statusByAddress.get(address.toLowerCase());
    return status?.isWhitelisted ?? false;
  };

  const getStatus = (address: string): WhitelistStatus | undefined => {
    return statusByAddress.get(address.toLowerCase());
  };

  return {
    statusByAddress,
    isWhitelisted,
    getStatus,
    isLoading,
    refetch: () => queries.forEach((q) => q.refetch()),
  };
}

export function useAllWalletTokenBalances(walletAddresses: string[]) {
  const queries = useQueries({
    queries: walletAddresses.map((address) => ({
      queryKey: tradingQueryKeys.walletBalances(address),
      queryFn: () => getWalletBalances(apiClient, address).then((res) => res.data),
      enabled: !!address,
      staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
      gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
    })),
  });

  const isLoading = queries.some((q) => q.isLoading);
  const error = queries.find((q) => q.error)?.error;

  const balancesByToken = new Map<string, Map<string, string>>();
  const tokenWallets = new Map<string, { walletAddress: string; balance: string }[]>();

  queries.forEach((query) => {
    if (query.data) {
      const { walletAddress, balances } = query.data;
      (balances || []).forEach((balance) => {
        if (!balancesByToken.has(balance.token)) {
          balancesByToken.set(balance.token, new Map());
        }
        balancesByToken.get(balance.token)!.set(walletAddress, balance.balance);

        if (!tokenWallets.has(balance.token)) {
          tokenWallets.set(balance.token, []);
        }
        tokenWallets.get(balance.token)!.push({
          walletAddress,
          balance: balance.balance,
        });
      });
    }
  });

  const hasHoldings = (tokenUuid: string): boolean => {
    return balancesByToken.has(tokenUuid);
  };

  const getTotalBalance = (tokenUuid: string): string => {
    const tokenBalances = balancesByToken.get(tokenUuid);
    if (!tokenBalances) return '0';
    let total = BigInt(0);
    tokenBalances.forEach((balance) => {
      total += BigInt(balance);
    });
    return total.toString();
  };

  const getWalletsWithHoldings = (tokenUuid: string): { walletAddress: string; balance: string }[] => {
    return tokenWallets.get(tokenUuid) || [];
  };

  return {
    balancesByToken,
    tokenWallets,
    hasHoldings,
    getTotalBalance,
    getWalletsWithHoldings,
    isLoading,
    error,
    refetch: () => queries.forEach((q) => q.refetch()),
  };
}

export function useAllUserOrders(walletAddresses: string[]) {
  const queries = useQueries({
    queries: walletAddresses.map((address) => ({
      queryKey: tradingQueryKeys.userOrders(address),
      queryFn: () => getUserOrders(apiClient, address).then((res) => res.data.results ?? []),
      enabled: !!address,
      staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
      gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
    })),
  });

  const isLoading = queries.some((q) => q.isLoading);
  const error = queries.find((q) => q.error)?.error;

  const allOrders = queries.flatMap((query) => query.data || []);

  allOrders.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  return {
    orders: allOrders as TransferOrder[],
    isLoading,
    error,
    refetch: () => queries.forEach((q) => q.refetch()),
  };
}

export function useShareTokens() {
  return useQuery({
    queryKey: tradingQueryKeys.tokens,
    queryFn: () => getShareTokens(apiClient).then((res) => res.data.results ?? []),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
  });
}

function useUserOrders(walletAddress: string | undefined) {
  return useQuery({
    queryKey: tradingQueryKeys.userOrders(walletAddress!),
    queryFn: () => getUserOrders(apiClient, walletAddress!).then((res) => res.data.results),
    enabled: !!walletAddress,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
  });
}

export function useOrderCreateMessage() {
  return useMutation({
    mutationFn: (data: CreateOrderRequest) => getOrderCreateMessage(apiClient, data).then((res) => res.data),
  });
}

export function useOrderCancelMessage() {
  return useMutation({
    mutationFn: (uuid: string) => getOrderCancelMessage(apiClient, uuid).then((res) => res.data),
  });
}

export function useCreateOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: SignedCreateOrderRequest) => createOrder(apiClient, data).then((res) => res.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trading', 'orders'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'userOrders'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'orderBook'] });
    },
  });
}

export function useCancelOrder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ uuid, ...signatureData }: { uuid: string } & SignedCancelOrderRequest) =>
      cancelOrder(apiClient, uuid, signatureData).then((res) => res.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trading', 'orders'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'userOrders'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'orderBook'] });
    },
  });
}

export function useOrderModificationMessage() {
  return useMutation({
    mutationFn: ({ orderUuid, modifications }: { orderUuid: string; modifications: OrderModificationRequest }) =>
      getOrderModificationMessage(apiClient, orderUuid, modifications).then((res) => res.data),
  });
}

export function useExecuteOrderModification() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ orderUuid, data }: { orderUuid: string; data: SignedOrderModificationRequest }) =>
      modifyOrder(apiClient, orderUuid, data).then((res) => res.data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['trading', 'orders'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'userOrders'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'orderBook'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'allOpenOrders'] });
      queryClient.invalidateQueries({ queryKey: tradingQueryKeys.orderModifications(variables.orderUuid) });
    },
  });
}

interface UseTradingOptions {
  tokenUuid?: string;
  walletAddress?: string;
  walletAddresses?: string[];
}

export function useTrading(options: UseTradingOptions = {}) {
  const { walletAddress, walletAddresses = [] } = options;

  const singleWalletOrdersQuery = useUserOrders(walletAddress);
  const multiWalletOrdersQuery = useAllUserOrders(walletAddresses);

  const useMultiWallet = walletAddresses.length > 0;
  const userOrders = useMultiWallet ? multiWalletOrdersQuery.orders : singleWalletOrdersQuery.data || [];
  const isLoadingUserOrders = useMultiWallet ? multiWalletOrdersQuery.isLoading : singleWalletOrdersQuery.isLoading;

  const tokenBalances = useAllWalletTokenBalances(walletAddresses);

  return {
    userOrders: userOrders as TransferOrder[],
    isLoadingUserOrders,
    hasHoldings: tokenBalances.hasHoldings,
    getWalletsWithHoldings: tokenBalances.getWalletsWithHoldings,
  };
}

export function useOrderBook(tokenUuid: string | undefined) {
  return useQuery({
    queryKey: ['trading', 'orderBook', tokenUuid] as const,
    queryFn: () => getOrderBook(apiClient, tokenUuid!).then((res) => res.data),
    enabled: !!tokenUuid,
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
    refetchInterval: TRADING_CONFIG.ORDER_BOOK_FALLBACK_INTERVAL,
  });
}
