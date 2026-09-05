import { useState, useCallback } from 'react';
import type { CreateWallet, DerivedAddress, HardwareWalletImport } from '@ledova/shared';
import { getChainByShortName } from '@ledova/shared';
import { useWalletsCrud } from './useWalletsCrud';
import type { SoftwareWalletImport } from '../../utils/softwareWallet';

/**
 * Screen-level hook for the Wallets screen.
 * Manages modal visibility and delegates CRUD operations to useWalletsCrud.
 * Form state is colocated in AddWalletModal.
 */
export function useWallets() {
  const crud = useWalletsCrud();

  // Modal visibility state
  const [showAddModal, setShowAddModal] = useState(false);
  const [preselectedChain, setPreselectedChain] = useState<'BTC' | 'ETH' | null>(null);

  // Add modal handlers
  const openAddModal = useCallback((chain: 'BTC' | 'ETH' | null = null) => {
    setPreselectedChain(chain);
    setShowAddModal(true);
  }, []);

  const closeAddModal = useCallback(() => {
    setShowAddModal(false);
    setPreselectedChain(null);
  }, []);

  const handleCreateWallet = useCallback(
    (data: CreateWallet) => {
      crud.createWallet(data, {
        onSuccess: () => closeAddModal(),
      });
    },
    [crud, closeAddModal],
  );

  const handleBatchCreateWallets = useCallback(
    (addresses: DerivedAddress[], importData: HardwareWalletImport) => {
      addresses.forEach((derivedAddress) => {
        // Find the matching parent key for this network type
        const parentKey = importData.parentKeys.find((pk) =>
          derivedAddress.derivationPath.startsWith(pk.parentDerivationPath),
        );

        // Get the chain code (e.g., "ethereum" or "bitcoin") from network type
        const chain = getChainByShortName(derivedAddress.networkType);
        if (!chain) return;

        crud.createWallet({
          userAccount: crud.userAccountUuid!,
          address: derivedAddress.address,
          chain: chain.code,
          walletType: 'hardware',
          derivationPath: derivedAddress.derivationPath,
          masterFingerprint: importData.masterFingerprint,
          addressIndex: derivedAddress.addressIndex,
          // Parent key data for deriving additional addresses
          parentPublicKey: parentKey?.parentPublicKey,
          parentChainCode: parentKey?.parentChainCode,
          parentDerivationPath: parentKey?.parentDerivationPath,
        });
      });
      closeAddModal();
    },
    [crud, closeAddModal],
  );

  const handleSoftwareWalletCreate = useCallback(
    (addresses: DerivedAddress[], importData: SoftwareWalletImport) => {
      addresses.forEach((derivedAddress) => {
        const parentKey = importData.parentKeys.find((pk) =>
          derivedAddress.derivationPath.startsWith(pk.parentDerivationPath),
        );

        const chain = getChainByShortName(derivedAddress.networkType);
        if (!chain) return;

        crud.createWallet({
          userAccount: crud.userAccountUuid!,
          address: derivedAddress.address,
          chain: chain.code,
          walletType: 'software',
          derivationPath: derivedAddress.derivationPath,
          masterFingerprint: importData.masterFingerprint,
          addressIndex: derivedAddress.addressIndex,
          parentPublicKey: parentKey?.parentPublicKey,
          parentChainCode: parentKey?.parentChainCode,
          parentDerivationPath: parentKey?.parentDerivationPath,
        });
      });
      closeAddModal();
    },
    [crud, closeAddModal],
  );

  return {
    // Data from CRUD hook
    userAccountUuid: crud.userAccountUuid,

    // Loading states
    isCreating: crud.isCreating,

    // Modal state
    showAddModal,
    preselectedChain,

    // Actions - CRUD
    handleCreateWallet,
    handleBatchCreateWallets,
    handleSoftwareWalletCreate,

    // Actions - Add modal
    openAddModal,
    closeAddModal,
  };
}
