import { useCallback, useRef, useState } from 'react';
import { Alert } from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getWallets,
  createWallet,
  updateWallet,
  deleteWallet,
  syncWallet,
  CACHE_TIMING,
  BLOCKCHAIN,
  calculateWalletTotals,
  filterWalletsByChain,
  getErrorMessage,
} from '@ledova/shared';
import type { CreateWallet } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';
import { invalidateHomeDashboard } from '../../utils/queryInvalidation';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { generateMockWalletsData } from './_mock/mock';
import { mockDataEnabled } from '../../_mock/mockDataEnabled';

export function useWalletsCrud() {
  const USE_MOCK_DATA = mockDataEnabled();
  const queryClient = useQueryClient();
  const { selectedAccount } = useUserPreferences();
  const [syncingWalletIds, setSyncingWalletIds] = useState<Set<string>>(() => new Set());
  const pendingSyncs = useRef(new Map<string, ReturnType<typeof syncWallet>>());

  const walletsQuery = useQuery({
    queryKey: ['wallets', selectedAccount?.uuid, { order_by: 'address_index' }],
    queryFn: () => getWallets(apiClient, { user_account: selectedAccount!.uuid, order_by: 'address_index' }),
    enabled: !USE_MOCK_DATA && !!selectedAccount?.uuid,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const invalidateHome = () => invalidateHomeDashboard(queryClient);

  const createMutation = useMutation({
    mutationFn: (data: CreateWallet) => createWallet(apiClient, data),
    onSuccess: () => {
      queryClient.refetchQueries({ queryKey: ['wallets'] });
      invalidateHome();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ uuid, name }: { uuid: string; name: string }) => updateWallet(apiClient, uuid, { name }),
    onSuccess: () => {
      queryClient.refetchQueries({ queryKey: ['wallets'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (uuid: string) => deleteWallet(apiClient, uuid, selectedAccount?.uuid),
    onSuccess: () => {
      queryClient.refetchQueries({ queryKey: ['wallets'] });
      invalidateHome();
    },
  });

  const syncMutation = useMutation({
    mutationFn: (uuid: string) => syncWallet(apiClient, uuid),
    onMutate: (uuid: string) => {
      setSyncingWalletIds((pending) => new Set(pending).add(uuid));
    },
    onSettled: (_data, _error, uuid) => {
      queryClient.refetchQueries({ queryKey: ['wallets'] });
      queryClient.refetchQueries({ queryKey: ['transactions'] });
      invalidateHome();
      setSyncingWalletIds((pending) => {
        const next = new Set(pending);
        next.delete(uuid);
        return next;
      });
    },
    onError: (error) => {
      Alert.alert(
        'Wallet not synced',
        getErrorMessage(error, 'Wallet sync could not finish. Please try again later.') ||
          'Wallet sync could not finish. Please try again later.',
      );
    },
  });

  const { mutateAsync } = syncMutation;
  const syncWalletOnce = useCallback(
    (uuid: string) => {
      const pending = pendingSyncs.current.get(uuid);
      if (pending) return pending;
      const request = mutateAsync(uuid).finally(() => pendingSyncs.current.delete(uuid));
      pendingSyncs.current.set(uuid, request);
      return request;
    },
    [mutateAsync],
  );

  const wallets = walletsQuery.data?.data.results || [];

  const btcWallets = filterWalletsByChain(wallets, BLOCKCHAIN.BITCOIN);
  const ethWallets = filterWalletsByChain(wallets, BLOCKCHAIN.ETHEREUM);
  const baseWallets = filterWalletsByChain(wallets, BLOCKCHAIN.BASE);
  const totals = calculateWalletTotals(wallets);

  if (USE_MOCK_DATA) {
    const mockWallets = generateMockWalletsData();
    const mockBtcWallets = filterWalletsByChain(mockWallets, BLOCKCHAIN.BITCOIN);
    const mockEthWallets = filterWalletsByChain(mockWallets, BLOCKCHAIN.ETHEREUM);
    const mockBaseWallets = filterWalletsByChain(mockWallets, BLOCKCHAIN.BASE);
    const mockTotals = calculateWalletTotals(mockWallets);

    return {
      wallets: mockWallets,
      btcWallets: mockBtcWallets,
      ethWallets: mockEthWallets,
      baseWallets: mockBaseWallets,
      totals: mockTotals,
      userAccountUuid: 'user-account-1',
      isLoading: false,
      isCreating: false,
      isUpdating: false,
      isDeleting: false,
      isSyncing: false,
      syncingWalletIds: new Set<string>(),
      createWallet: (_data: CreateWallet, options?: { onSuccess?: () => void }) => {
        options?.onSuccess?.();
      },
      updateWallet: (_uuid: string, _name: string, options?: { onSuccess?: () => void }) => {
        options?.onSuccess?.();
      },
      deleteWallet: (_uuid: string, options?: { onSuccess?: () => void }) => {
        options?.onSuccess?.();
      },
      syncWallet: async (_uuid: string) => undefined,
      refetch: async () => ({ data: undefined, error: null }),
    };
  }

  return {
    wallets,
    btcWallets,
    ethWallets,
    baseWallets,
    totals,
    userAccountUuid: selectedAccount?.uuid,

    isLoading: walletsQuery.isLoading,
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isSyncing: syncingWalletIds.size > 0,
    syncingWalletIds,

    createWallet: createMutation.mutate,
    updateWallet: (uuid: string, name: string, options?: { onSuccess?: () => void }) =>
      updateMutation.mutate({ uuid, name }, options),
    deleteWallet: deleteMutation.mutate,
    syncWallet: syncWalletOnce,

    refetch: walletsQuery.refetch,
  };
}
