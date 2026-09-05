import { useState, useMemo } from 'react';
import { getChainName, BLOCKCHAIN, WALLET_TYPE } from '@ledova/shared';
import type { Wallet } from '@ledova/shared';
import type { WalletChainFilter, WalletSortOption } from './WalletSortModal';

const CHAIN_MAP: Record<Exclude<WalletChainFilter, 'all'>, string> = {
  btc: BLOCKCHAIN.BITCOIN,
  eth: BLOCKCHAIN.ETHEREUM,
  base: BLOCKCHAIN.BASE,
};

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
        const aHasName = a.name ? 0 : 1;
        const bHasName = b.name ? 0 : 1;
        if (aHasName !== bHasName) return aHasName - bHasName;
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
      case 'highestValue': {
        return parseFloat(b.marketValue || '0') - parseFloat(a.marketValue || '0');
      }
      case 'highestBalance': {
        return parseFloat(b.nativeBalance || '0') - parseFloat(a.nativeBalance || '0');
      }
      default:
        return 0;
    }
  });
}

export function useWalletSort(wallets: Wallet[], initialSort: WalletSortOption = 'default') {
  const [chainFilter, setChainFilter] = useState<WalletChainFilter>('all');
  const [sortOption, setSortOption] = useState<WalletSortOption>(initialSort);
  const [showSortModal, setShowSortModal] = useState(false);

  const sortedWallets = useMemo(() => {
    let filtered = wallets;

    if (chainFilter !== 'all') {
      const targetChain = CHAIN_MAP[chainFilter];
      filtered = wallets.filter((w) => getChainName(w.chain) === targetChain);
    }

    return sortWallets(filtered, sortOption);
  }, [wallets, chainFilter, sortOption]);

  const isFiltered = chainFilter !== 'all' || sortOption !== 'default';

  const handleApply = (chain: WalletChainFilter, sort: WalletSortOption) => {
    setChainFilter(chain);
    setSortOption(sort);
  };

  return {
    sortedWallets,
    chainFilter,
    sortOption,
    isFiltered,
    showSortModal,
    setShowSortModal,
    handleApply,
  };
}
