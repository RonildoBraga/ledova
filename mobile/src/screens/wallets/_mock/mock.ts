import type { Wallet } from '@ledova/shared';

const MOCK_WALLETS_PER_CHAIN = 30;

const BTC_NAMES = [
  'Main BTC Wallet',
  'Savings',
  'Trading BTC',
  'Cold Storage BTC',
  'DCA Fund',
  'Lightning Ready',
  'Inheritance',
  'Business BTC',
  'Mining Rewards',
  'Stack Sats',
  null,
  null,
  null,
  null,
  null,
];

const ETH_NAMES = [
  'Trading Wallet',
  'Cold Storage',
  'DeFi Wallet',
  'NFT Vault',
  'Staking ETH',
  'Gas Wallet',
  'DAO Treasury',
  'Airdrop Catcher',
  'MEV Wallet',
  'Bridge Wallet',
  null,
  null,
  null,
  null,
  null,
];

function randomBalance(min: number, max: number): string {
  return (Math.random() * (max - min) + min).toFixed(6);
}

function randomMarketValue(balance: string, pricePerUnit: number): string {
  return (parseFloat(balance) * pricePerUnit).toFixed(2);
}

function randomStatus(): 'VERIFIED' | 'PENDING' {
  return Math.random() > 0.3 ? 'VERIFIED' : 'PENDING';
}

function randomWalletType(): 'hardware' | 'software' {
  return Math.random() > 0.4 ? 'hardware' : 'software';
}

function makeBtcAddress(index: number): string {
  const hex = index.toString(16).padStart(8, '0');
  return `tb1q${hex}${'abcdef1234567890'.repeat(2).slice(0, 30)}`;
}

function makeEthAddress(index: number): string {
  const hex = index.toString(16).padStart(8, '0');
  return `0x${hex}${'AbCdEf1234567890'.repeat(3).slice(0, 32)}`;
}

export const generateMockWalletsData = (): Wallet[] => {
  const wallets: Wallet[] = [];
  const BTC_PRICE = 45000;
  const ETH_PRICE = 3500;

  for (let i = 0; i < MOCK_WALLETS_PER_CHAIN; i++) {
    const balance = randomBalance(0.001, 2.5);
    const status = randomStatus();
    const walletType = randomWalletType();
    const fingerprint = `btcfp${String(Math.floor(i / 5)).padStart(2, '0')}`;
    const parentPath = `m/84'/1'/${Math.floor(i / 5)}'`;

    wallets.push({
      uuid: `wallet-btc-${i}`,
      userAccount: 'user-account-1',
      name: BTC_NAMES[i % BTC_NAMES.length] ?? undefined,
      address: makeBtcAddress(i),
      chain: 'Bitcoin',
      walletType,
      verificationStatus: status,
      verifiedAt:
        status === 'VERIFIED' ? new Date(Date.now() - (i + 1) * 2 * 24 * 60 * 60 * 1000).toISOString() : undefined,
      verificationChallenge: status === 'PENDING' ? `verify-btc-${i}` : undefined,
      nativeBalance: balance,
      nativeMarketValue: randomMarketValue(balance, BTC_PRICE),
      marketValue: randomMarketValue(balance, BTC_PRICE),
      lastSyncedAt: new Date(Date.now() - i * 60 * 60 * 1000).toISOString(),
      derivationPath: `${parentPath}/0/${i % 5}`,
      addressIndex: i % 5,
      masterFingerprint: fingerprint,
      parentPublicKey: walletType === 'hardware' ? `xpub-btc-${fingerprint}` : undefined,
      parentChainCode: walletType === 'hardware' ? `chain-btc-${fingerprint}` : undefined,
      parentDerivationPath: walletType === 'hardware' ? parentPath : undefined,
      createdAt: new Date(Date.now() - (90 - i) * 24 * 60 * 60 * 1000).toISOString(),
      updatedAt: new Date(Date.now() - i * 60 * 60 * 1000).toISOString(),
    });
  }

  for (let i = 0; i < MOCK_WALLETS_PER_CHAIN; i++) {
    const balance = randomBalance(0.01, 10);
    const status = randomStatus();
    const walletType = randomWalletType();
    const fingerprint = `ethfp${String(Math.floor(i / 5)).padStart(2, '0')}`;
    const parentPath = `m/44'/60'/${Math.floor(i / 5)}'`;

    wallets.push({
      uuid: `wallet-eth-${i}`,
      userAccount: 'user-account-1',
      name: ETH_NAMES[i % ETH_NAMES.length] ?? undefined,
      address: makeEthAddress(i),
      chain: 'Ethereum',
      walletType,
      verificationStatus: status,
      verifiedAt:
        status === 'VERIFIED' ? new Date(Date.now() - (i + 1) * 3 * 24 * 60 * 60 * 1000).toISOString() : undefined,
      verificationChallenge: status === 'PENDING' ? `verify-eth-${i}` : undefined,
      nativeBalance: balance,
      nativeMarketValue: randomMarketValue(balance, ETH_PRICE),
      marketValue: randomMarketValue(balance, ETH_PRICE),
      lastSyncedAt: new Date(Date.now() - i * 30 * 60 * 1000).toISOString(),
      derivationPath: `${parentPath}/0/${i % 5}`,
      addressIndex: i % 5,
      masterFingerprint: fingerprint,
      parentPublicKey: walletType === 'hardware' ? `xpub-eth-${fingerprint}` : undefined,
      parentChainCode: walletType === 'hardware' ? `chain-eth-${fingerprint}` : undefined,
      parentDerivationPath: walletType === 'hardware' ? parentPath : undefined,
      createdAt: new Date(Date.now() - (90 - i) * 24 * 60 * 60 * 1000).toISOString(),
      updatedAt: new Date(Date.now() - i * 30 * 60 * 1000).toISOString(),
    });
  }

  return wallets;
};
