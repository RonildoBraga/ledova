import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getWallets, createWallet, updateWallet, deleteWallet, syncWallet } from '@ledova/shared-services';
import { CACHE_TIMING, BLOCKCHAIN } from '@ledova/shared-constants';
import type { CreateWallet } from '@ledova/shared-types';
import { calculateWalletTotals, filterWalletsByChain } from '@ledova/shared-utils';
import { apiClient } from '../../services/apiClient';
import { invalidateHomeDashboard } from '../../utils/queryInvalidation';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { generateMockWalletsData } from './_mock/mock';
import { useMockData } from '../../_mock/useMockData';

export function useWalletsCrud() {
  const USE_MOCK_DATA = useMockData();
  const queryClient = useQueryClient();
  const { selectedAccount } = useUserPreferences();
  const [syncingWalletId, setSyncingWalletId] = useState<string | undefined>(undefined);

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
      setSyncingWalletId(uuid);
    },
    onSuccess: () => {
      queryClient.refetchQueries({ queryKey: ['wallets'] });
      queryClient.refetchQueries({ queryKey: ['transactions'] });
      invalidateHome();
    },
    onSettled: () => {
      setSyncingWalletId(undefined);
    },
  });

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
      syncingWalletId: undefined,
      createWallet: (_data: CreateWallet, options?: { onSuccess?: () => void }) => {
        options?.onSuccess?.();
      },
      updateWallet: (_uuid: string, _name: string, options?: { onSuccess?: () => void }) => {
        options?.onSuccess?.();
      },
      deleteWallet: (_uuid: string, options?: { onSuccess?: () => void }) => {
        options?.onSuccess?.();
      },
      syncWallet: () => {},
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
    isSyncing: syncMutation.isPending,
    syncingWalletId,

    createWallet: createMutation.mutate,
    updateWallet: (uuid: string, name: string, options?: { onSuccess?: () => void }) =>
      updateMutation.mutate({ uuid, name }, options),
    deleteWallet: deleteMutation.mutate,
    syncWallet: syncMutation.mutateAsync,

    refetch: walletsQuery.refetch,
  };
}
