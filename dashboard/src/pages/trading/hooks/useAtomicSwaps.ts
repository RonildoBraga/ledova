import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CACHE_TIMING,
  TRADING_ENDPOINTS,
  getSwapOrders,
  getOrderSwapData,
  submitOrderSwapSignature,
  getOrderSwapApprovalStatus,
  getOrderSwapApprovalData,
} from '@ledova/shared';
import type { SubmitSignatureRequest, SwapOrder } from '@ledova/shared';
import apiClient from '@services/apiClient';

export interface BroadcastResponse {
  txHash: string;
  blockNumber: number;
  gasUsed: number;
}

export const swapQueryKeys = {
  swaps: (walletAddress: string) => ['trading', 'swaps', walletAddress] as const,
  swapsMulti: (walletAddresses: string[]) => ['trading', 'swaps', 'multi', walletAddresses] as const,
  orderSwapData: (orderUuid: string, walletAddress: string) =>
    ['trading', 'orderSwapData', orderUuid, walletAddress] as const,
  orderSwapApprovalStatus: (orderUuid: string, walletAddress: string) =>
    ['trading', 'orderSwapApprovalStatus', orderUuid, walletAddress] as const,
  orderSwapApprovalData: (orderUuid: string, walletAddress: string) =>
    ['trading', 'orderSwapApprovalData', orderUuid, walletAddress] as const,
};

export function useSwapOrdersMulti(walletAddresses: string[]) {
  return useQuery({
    queryKey: swapQueryKeys.swapsMulti(walletAddresses),
    queryFn: async () => {
      if (walletAddresses.length === 0) return [] as SwapOrder[];
      const results = await Promise.all(
        walletAddresses.map((addr) => getSwapOrders(apiClient, addr).then((res) => res.data.results as SwapOrder[])),
      );
      const swapMap = new Map<string, SwapOrder>();
      results.flat().forEach((swap) => {
        if (!swapMap.has(swap.uuid)) {
          swapMap.set(swap.uuid, swap);
        }
      });
      return Array.from(swapMap.values());
    },
    enabled: walletAddresses.length > 0,
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
    gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
  });
}

export function useOrderSwapData(orderUuid: string | undefined, walletAddress: string | undefined) {
  return useQuery({
    queryKey: swapQueryKeys.orderSwapData(orderUuid || '', walletAddress || ''),
    queryFn: () => getOrderSwapData(apiClient, orderUuid!, { walletAddress: walletAddress! }).then((res) => res.data),
    enabled: !!orderUuid && !!walletAddress,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
  });
}

export function useSubmitOrderSwapSignature() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ orderUuid, data }: { orderUuid: string; data: SubmitSignatureRequest }) =>
      submitOrderSwapSignature(apiClient, orderUuid, data).then((res) => res.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trading', 'swaps'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'swapData'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'orderSwapData'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'userOrders'] });
    },
  });
}

export function useOrderSwapApprovalStatus(orderUuid: string | undefined, walletAddress: string | undefined) {
  return useQuery({
    queryKey: swapQueryKeys.orderSwapApprovalStatus(orderUuid || '', walletAddress || ''),
    queryFn: () => getOrderSwapApprovalStatus(apiClient, orderUuid!, walletAddress!).then((res) => res.data),
    enabled: !!orderUuid && !!walletAddress,
    staleTime: 5000, // Check frequently as approval state can change
    gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
  });
}

export function useOrderSwapApprovalData(orderUuid: string | undefined, walletAddress: string | undefined) {
  return useQuery({
    queryKey: swapQueryKeys.orderSwapApprovalData(orderUuid || '', walletAddress || ''),
    queryFn: () => getOrderSwapApprovalData(apiClient, orderUuid!, walletAddress!).then((res) => res.data),
    enabled: !!orderUuid && !!walletAddress,
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
    gcTime: CACHE_TIMING.DEFAULT_GC_TIME,
  });
}

export function useBroadcastTransaction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (signedTx: string) => {
      const response = await apiClient.post<BroadcastResponse>(TRADING_ENDPOINTS.TRANSFERS.BROADCAST, {
        signedTransaction: signedTx,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trading', 'orderSwapApprovalStatus'] });
      queryClient.invalidateQueries({ queryKey: ['trading', 'orderSwapApprovalData'] });
    },
  });
}
