import { useState, useCallback } from 'react';
import { apiClient } from '../services/apiClient';
import { fetchBatchBalances, isEthereumChain, isBitcoinChain } from '@ledova/shared';
import type { DerivedAddress } from '@ledova/shared';

export function useFetchBalances() {
  const [balances, setBalances] = useState<Map<string, string>>(new Map());
  const [isLoadingBalances, setIsLoadingBalances] = useState(false);

  const fetchBalances = useCallback(async (addressList: DerivedAddress[]) => {
    setIsLoadingBalances(true);
    const ethAddresses = addressList.filter((a) => isEthereumChain(a.networkType));
    const btcAddresses = addressList.filter((a) => isBitcoinChain(a.networkType));

    const newBalances = new Map<string, string>();

    if (ethAddresses.length > 0) {
      try {
        const ethAddrs = ethAddresses.map((a) => a.address);
        const ethResponse = await fetchBatchBalances(apiClient, ethAddrs, 'ETH');
        ethAddresses.forEach((addr) => {
          const balance = ethResponse.balances[addr.address] || '0';
          newBalances.set(addr.address, `${balance} ETH`);
        });
      } catch {
        ethAddresses.forEach((addr) => newBalances.set(addr.address, '0 ETH'));
      }
    }

    if (btcAddresses.length > 0) {
      try {
        const btcAddrs = btcAddresses.map((a) => a.address);
        const btcResponse = await fetchBatchBalances(apiClient, btcAddrs, 'BTC');
        btcAddresses.forEach((addr) => {
          const balance = btcResponse.balances[addr.address] || '0';
          newBalances.set(addr.address, `${balance} BTC`);
        });
      } catch {
        btcAddresses.forEach((addr) => newBalances.set(addr.address, '0 BTC'));
      }
    }

    setBalances(newBalances);
    setIsLoadingBalances(false);
  }, []);

  return { balances, isLoadingBalances, fetchBalances };
}
