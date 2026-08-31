import { getChainName, BLOCKCHAIN } from '@ledova/shared-constants';
import type { Wallet, WalletTotals } from '@ledova/shared-types';

export function calculateWalletTotals(wallets: Wallet[]): WalletTotals {
  return wallets.reduce(
    (acc, wallet) => {
      const balance = parseFloat(wallet.nativeBalance) || 0;
      const nativeMarketValue = parseFloat(wallet.nativeMarketValue) || 0;
      const totalMarketValue = parseFloat(wallet.marketValue) || 0;
      const chain = getChainName(wallet.chain);

      if (chain === BLOCKCHAIN.BITCOIN) {
        acc.btc += balance;
        acc.btcMarketValue += nativeMarketValue;
        acc.btcTotalMarketValue += totalMarketValue;
      } else if (chain === BLOCKCHAIN.ETHEREUM) {
        acc.eth += balance;
        acc.ethMarketValue += nativeMarketValue;
        acc.ethTotalMarketValue += totalMarketValue;
      }

      return acc;
    },
    { btc: 0, eth: 0, btcMarketValue: 0, ethMarketValue: 0, btcTotalMarketValue: 0, ethTotalMarketValue: 0 },
  );
}

export function filterWalletsByChain(wallets: Wallet[], blockchain: string): Wallet[] {
  return wallets.filter((w) => getChainName(w.chain) === blockchain);
}
