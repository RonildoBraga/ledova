import { useState, useMemo } from 'react';
import { WALLET_TYPE } from '@ledova/shared';
import type { Wallet } from '@ledova/shared';

export type WalletSortOption = 'default' | 'verified' | 'name' | 'namedFirst' | 'highestValue' | 'highestBalance';

function sortWallets(wallets: Wallet[], option: WalletSortOption): Wallet[] {
  if (option === 'default') {
    return [...wallets].sort((a, b) => {
      const aIsHardware = !a.walletType || a.walletType === WALLET_TYPE.HARDWARE;
      const bIsHardware = !b.walletType || b.walletType === WALLET_TYPE.HARDWARE;
      if (aIsHardware === bIsHardware) return 0;
      return aIsHardware ? -1 : 1;
    });
  }

  return [...wallets].sort((a, b) => {
    switch (option) {
      case 'verified': {
        const aVerified = a.verificationStatus === 'VERIFIED' ? 0 : 1;
        const bVerified = b.verificationStatus === 'VERIFIED' ? 0 : 1;
        if (aVerified !== bVerified) return aVerified - bVerified;
        const aLabel = (a.name || a.address).toLowerCase();
        const bLabel = (b.name || b.address).toLowerCase();
        return aLabel.localeCompare(bLabel);
      }
      case 'name': {
        const aLabel = (a.name || a.address).toLowerCase();
        const bLabel = (b.name || b.address).toLowerCase();
        return aLabel.localeCompare(bLabel);
      }
      case 'namedFirst': {
        const aHasName = a.name ? 0 : 1;
        const bHasName = b.name ? 0 : 1;
        if (aHasName !== bHasName) return aHasName - bHasName;
        const aLabel = (a.name || a.address).toLowerCase();
        const bLabel = (b.name || b.address).toLowerCase();
        return aLabel.localeCompare(bLabel);
      }
      case 'highestValue':
        return parseFloat(b.marketValue || '0') - parseFloat(a.marketValue || '0');
      case 'highestBalance':
        return parseFloat(b.nativeBalance || '0') - parseFloat(a.nativeBalance || '0');
      default:
        return 0;
    }
  });
}

export function useWalletSort(wallets: Wallet[]) {
  const [sortOption, setSortOption] = useState<WalletSortOption>('default');
  const [showSortModal, setShowSortModal] = useState(false);

  const sortedWallets = useMemo(() => sortWallets(wallets, sortOption), [wallets, sortOption]);

  const isFiltered = sortOption !== 'default';

  const handleApply = (sort: WalletSortOption) => {
    setSortOption(sort);
  };

  return {
    sortedWallets,
    sortOption,
    isFiltered,
    showSortModal,
    setShowSortModal,
    handleApply,
  };
}
