import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getWallets,
  createWallet,
  updateWallet,
  deleteWallet,
  syncWallet,
  CACHE_TIMING,
  getChainByShortName,
} from '@ledova/shared';
import apiClient from '@services/apiClient';
import { useSelectedPortfolio } from '@hooks/useSelectedPortfolio';
import type { Wallet, CreateWallet, DerivedAddress, HardwareWalletImport } from '@ledova/shared';

export function useWallets() {
  const queryClient = useQueryClient();
  const { portfolio } = useSelectedPortfolio();
  const [derivingWallet, setDerivingWallet] = useState<Wallet | null>(null);

  const walletsQuery = useQuery({
    queryKey: ['wallets', portfolio?.userAccount, { order_by: 'address_index' }],
    queryFn: () => getWallets(apiClient, { user_account: portfolio!.userAccount, order_by: 'address_index' }),
    enabled: !!portfolio?.userAccount,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const createMutation = useMutation({
    mutationFn: (data: CreateWallet) => createWallet(apiClient, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ uuid, name }: { uuid: string; name: string }) => updateWallet(apiClient, uuid, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (uuid: string) => deleteWallet(apiClient, uuid, portfolio?.userAccount),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] });
    },
  });

  const handleCreateWallet = useCallback(
    (data: CreateWallet) => {
      createMutation.mutate(data);
    },
    [createMutation],
  );

  const handleBatchCreateWallets = useCallback(
    async (addresses: DerivedAddress[], importData: HardwareWalletImport) => {
      if (!portfolio?.userAccount) return;

      for (let i = 0; i < addresses.length; i++) {
        const addr = addresses[i];
        const parentKey = importData.parentKeys[i];

        const chain = getChainByShortName(addr.networkType);
        if (!chain) continue;

        const walletData: CreateWallet = {
          userAccount: portfolio.userAccount,
          address: addr.address,
          chain: chain.code,
          derivationPath: addr.derivationPath,
          masterFingerprint: importData.masterFingerprint,
          addressIndex: addr.addressIndex,
        };

        if (parentKey) {
          walletData.parentPublicKey = parentKey.parentPublicKey;
          walletData.parentChainCode = parentKey.parentChainCode;
          walletData.parentDerivationPath = parentKey.parentDerivationPath;
        }

        createMutation.mutate(walletData);
      }
    },
    [portfolio?.userAccount, createMutation],
  );

  const handleUpdateWalletName = useCallback(
    (uuid: string, name: string) => updateMutation.mutate({ uuid, name }),
    [updateMutation],
  );

  const handleDeleteWallet = useCallback((uuid: string) => deleteMutation.mutate(uuid), [deleteMutation]);

  const syncMutation = useMutation({
    mutationFn: (uuid: string) => syncWallet(apiClient, uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallets'] });
    },
  });

  const handleSyncWallet = useCallback((uuid: string) => syncMutation.mutate(uuid), [syncMutation]);

  const openDeriveModal = useCallback((wallet: Wallet) => {
    setDerivingWallet(wallet);
  }, []);

  const closeDeriveModal = useCallback(() => {
    setDerivingWallet(null);
  }, []);

  const handleDeriveAddress = useCallback(
    (derivedAddress: DerivedAddress) => {
      if (!derivingWallet || !portfolio?.userAccount) return;

      createMutation.mutate(
        {
          userAccount: portfolio.userAccount,
          address: derivedAddress.address,
          chain: derivingWallet.chain,
          derivationPath: derivedAddress.derivationPath,
          masterFingerprint: derivingWallet.masterFingerprint,
          addressIndex: derivedAddress.addressIndex,
          parentPublicKey: derivingWallet.parentPublicKey,
          parentChainCode: derivingWallet.parentChainCode,
          parentDerivationPath: derivingWallet.parentDerivationPath,
        },
        {
          onSuccess: () => {
            setDerivingWallet(null);
          },
        },
      );
    },
    [derivingWallet, portfolio?.userAccount, createMutation],
  );

  const wallets = walletsQuery.data?.data.results || [];

  const canDeriveAddress = useCallback(
    (wallet: Wallet): boolean => {
      if (!wallet.parentPublicKey || !wallet.parentChainCode || !wallet.parentDerivationPath) return false;
      const nextIndex = (wallet.addressIndex ?? 0) + 1;
      const parentKey = `${wallet.masterFingerprint}:${wallet.parentDerivationPath}`;
      const nextExists = wallets.some((w) => {
        if (!w.masterFingerprint || !w.parentDerivationPath) return false;
        return `${w.masterFingerprint}:${w.parentDerivationPath}` === parentKey && w.addressIndex === nextIndex;
      });
      return !nextExists;
    },
    [wallets],
  );

  return {
    wallets,
    userAccountUuid: portfolio?.userAccount,
    derivingWallet,
    isLoading: walletsQuery.isLoading,
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isSyncing: syncMutation.isPending,
    handleCreateWallet,
    handleBatchCreateWallets,
    handleUpdateWalletName,
    handleDeleteWallet,
    handleSyncWallet,
    openDeriveModal,
    closeDeriveModal,
    handleDeriveAddress,
    canDeriveAddress,
  };
}
