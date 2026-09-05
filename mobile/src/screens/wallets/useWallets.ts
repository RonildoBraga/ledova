import { useState, useCallback } from 'react';
import type { CreateWallet, DerivedAddress, HardwareWalletImport } from '@ledova/shared';
import { getChainByShortName } from '@ledova/shared';
import { useWalletsCrud } from './useWalletsCrud';
import type { SoftwareWalletImport } from '../../utils/softwareWallet';

export function useWallets() {
  const crud = useWalletsCrud();

  const [showAddModal, setShowAddModal] = useState(false);
  const [preselectedChain, setPreselectedChain] = useState<'BTC' | 'ETH' | null>(null);

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
        const parentKey = importData.parentKeys.find((pk) =>
          derivedAddress.derivationPath.startsWith(pk.parentDerivationPath),
        );

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
    userAccountUuid: crud.userAccountUuid,

    isCreating: crud.isCreating,

    showAddModal,
    preselectedChain,

    handleCreateWallet,
    handleBatchCreateWallets,
    handleSoftwareWalletCreate,

    openAddModal,
    closeAddModal,
  };
}
