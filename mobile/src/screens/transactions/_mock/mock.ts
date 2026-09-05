import type { Transaction } from '@ledova/shared';

interface MockTransactionPage {
  results: Transaction[];
  count: number;
  next: string | null;
  previous: string | null;
}

const TRANSACTION_TYPES = ['incoming', 'outgoing'] as const;
const ASSETS = [
  { symbol: 'BTC', name: 'Bitcoin' },
  { symbol: 'ETH', name: 'Ethereum' },
  { symbol: 'SOL', name: 'Solana' },
  { symbol: 'MATIC', name: 'Polygon' },
  { symbol: 'TST1', name: 'Synthetic Test Token 1' },
  { symbol: 'TST2', name: 'Synthetic Test Token 2' },
];

const CHAINS = ['Bitcoin', 'Ethereum', 'Polygon', 'Solana'];

const WALLET_ADDRESSES = {
  Bitcoin: ['tb1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh', 'tb1q34567890abcdefghijklmnopqrstuvwxyz12345'],
  Ethereum: ['0x0000000000000000000000000000000000000101', '0x0000000000000000000000000000000000000102'],
  Polygon: ['0x0000000000000000000000000000000000000201', '0x0000000000000000000000000000000000000202'],
  Solana: ['mock-solana-wallet-01', 'mock-solana-wallet-02'],
};

const EXTERNAL_ADDRESSES = [
  '0x0000000000000000000000000000000000000301',
  '0x0000000000000000000000000000000000000302',
  'tb1q9876543210987654321098765432109876543',
  'mock-solana-external-01',
];

const generateTransactionHash = (index: number): string => {
  const hash = `0x${index.toString(16).padStart(64, '0')}`;
  return hash;
};

const generateBlockTimestamp = (daysAgo: number): string => {
  const now = new Date();
  const date = new Date(now.getTime() - daysAgo * 24 * 60 * 60 * 1000);
  return date.toISOString();
};

const generateAmount = (assetSymbol: string): string => {
  const baseAmounts: Record<string, { min: number; max: number }> = {
    BTC: { min: 0.001, max: 1.5 },
    ETH: { min: 0.01, max: 5 },
    SOL: { min: 1, max: 500 },
    MATIC: { min: 10, max: 5000 },
    TST1: { min: 100, max: 50000 },
    TST2: { min: 100, max: 50000 },
  };

  const range = baseAmounts[assetSymbol] || { min: 1, max: 1000 };
  const amount = Math.random() * (range.max - range.min) + range.min;

  // More decimal places for smaller amounts
  const decimals = amount < 1 ? 8 : amount < 100 ? 4 : 2;
  return amount.toFixed(decimals);
};

const generateTransactionFee = (chain: string): string => {
  const baseFees: Record<string, { min: number; max: number }> = {
    Bitcoin: { min: 0.00001, max: 0.0005 },
    Ethereum: { min: 0.001, max: 0.05 },
    Polygon: { min: 0.0001, max: 0.01 },
    Solana: { min: 0.000005, max: 0.00001 },
  };

  const range = baseFees[chain] || { min: 0.0001, max: 0.01 };
  const fee = Math.random() * (range.max - range.min) + range.min;
  return fee.toFixed(8);
};

export const generateMockTransactionsData = (pageSize = 20, page = 1): MockTransactionPage => {
  const totalTransactions = 150;
  const startIndex = (page - 1) * pageSize;
  const endIndex = Math.min(startIndex + pageSize, totalTransactions);
  const hasNext = endIndex < totalTransactions;
  const hasPrevious = page > 1;

  const transactions: Transaction[] = [];

  for (let i = startIndex; i < endIndex; i++) {
    const daysAgo = Math.floor(i / 3); // Roughly 3 transactions per day
    const asset = ASSETS[Math.floor(Math.random() * ASSETS.length)];
    const chain = CHAINS[Math.floor(Math.random() * CHAINS.length)];
    const direction = TRANSACTION_TYPES[Math.floor(Math.random() * 2)];
    const walletAddresses = WALLET_ADDRESSES[chain as keyof typeof WALLET_ADDRESSES] || WALLET_ADDRESSES.Ethereum;
    const walletAddress = walletAddresses[Math.floor(Math.random() * walletAddresses.length)];
    const externalAddress = EXTERNAL_ADDRESSES[Math.floor(Math.random() * EXTERNAL_ADDRESSES.length)];

    const fromAddress = direction === 'outgoing' ? walletAddress : externalAddress;
    const toAddress = direction === 'outgoing' ? externalAddress : walletAddress;

    transactions.push({
      uuid: `tx-${i + 1}`,
      txHash: generateTransactionHash(i),
      chain,
      fromAddress,
      toAddress,
      asset: asset.symbol,
      assetSymbol: asset.symbol,
      assetName: asset.name,
      amount: generateAmount(asset.symbol),
      blockTimestamp: generateBlockTimestamp(daysAgo),
      blockNumber: 18000000 + i * 100,
      status: Math.random() > 0.05 ? 'confirmed' : 'pending',
      transactionFee: generateTransactionFee(chain),
      transactionFeeEstimated: generateTransactionFee(chain),
      wallet: `wallet-${(i % 4) + 1}`,
      walletAddress,
      createdAt: generateBlockTimestamp(daysAgo),
      updatedAt: generateBlockTimestamp(daysAgo),
    });
  }

  return {
    results: transactions,
    count: totalTransactions,
    next: hasNext ? `page=${page + 1}` : null,
    previous: hasPrevious ? `page=${page - 1}` : null,
  };
};
