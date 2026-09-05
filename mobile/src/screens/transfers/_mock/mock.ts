import type { TransferableAsset, TransactionData, Wallet } from '@ledova/shared';

export const generateMockTransferableAssets = (wallet: Wallet): TransferableAsset[] => {
  const assets: TransferableAsset[] = [];

  const isEthereum = wallet.chain === 'Ethereum';
  const isBitcoin = wallet.chain === 'Bitcoin';

  if (isEthereum) {
    assets.push({
      uuid: `native-${wallet.uuid}`,
      symbol: 'ETH',
      name: 'Ethereum',
      balance: wallet.nativeBalance,
      marketValue: wallet.nativeMarketValue,
      isNative: true,
      decimals: 18,
      chain: 'Ethereum',
    });

    assets.push(
      {
        uuid: 'usdc-holding-1',
        symbol: 'TST1',
        name: 'Synthetic Test USD',
        balance: '1000.00',
        marketValue: '1000.00',
        isNative: false,
        contractAddress: '0x0000000000000000000000000000000000001001',
        decimals: 6,
        chain: 'Ethereum',
      },
      {
        uuid: 'usdt-holding-1',
        symbol: 'TST2',
        name: 'Synthetic Test USD 2',
        balance: '500.00',
        marketValue: '500.00',
        isNative: false,
        contractAddress: '0x0000000000000000000000000000000000001002',
        decimals: 6,
        chain: 'Ethereum',
      },
    );
  } else if (isBitcoin) {
    assets.push({
      uuid: `native-${wallet.uuid}`,
      symbol: 'BTC',
      name: 'Bitcoin',
      balance: wallet.nativeBalance,
      marketValue: wallet.nativeMarketValue,
      isNative: true,
      decimals: 8,
      chain: 'Bitcoin',
    });
  }

  return assets;
};

const generateMockEthereumTransactionData = (
  fromAddress: string,
  toAddress: string,
  amount: string,
  isNative: boolean = true,
): TransactionData => {
  const gasPrice = '20000000000';
  const gasLimit = isNative ? 21000 : 65000;
  const gasCost = (parseInt(gasPrice) * gasLimit) / 1e18;
  const gasPriceGwei = (parseInt(gasPrice) / 1e9).toString();

  const transaction = {
    chainId: 11155111,
    nonce: 42,
    to: toAddress,
    value: isNative ? amount : '0',
    data: isNative
      ? '0x'
      : `0xa9059cbb000000000000000000000000${toAddress.slice(2)}${parseInt(amount).toString(16).padStart(64, '0')}`,
    gasPrice,
    gasLimit: gasLimit.toString(),
  };

  return {
    fromAddress,
    toAddress,
    amountEth: isNative ? amount : undefined,
    amountToken: !isNative ? amount : undefined,
    tokenSymbol: !isNative ? 'TST1' : undefined,
    gasCostEth: gasCost.toString(),
    totalCostEth: (parseFloat(amount) + gasCost).toString(),
    gasPriceGwei,
    gasLimit: gasLimit.toString(),
    transaction: transaction as unknown,
  } as TransactionData;
};

const generateMockBitcoinTransactionData = (
  fromAddress: string,
  toAddress: string,
  amount: string,
): TransactionData => {
  const feeRate = 50;
  const estimatedSize = 250;
  const feeSats = feeRate * estimatedSize;
  const feeBtc = feeSats / 1e8;

  const transaction = {
    inputs: [
      {
        txid: 'abc123def456...',
        vout: 0,
        value: '50000000',
      },
    ],
    outputs: [
      {
        address: toAddress,
        value: (parseFloat(amount) * 1e8).toString(),
      },
    ],
    feeRate,
    estimatedSize,
  };

  return {
    fromAddress,
    toAddress,
    amountBtc: amount,
    feeBtc: feeBtc.toString(),
    totalCostBtc: (parseFloat(amount) + feeBtc).toString(),
    transaction: transaction as unknown,
  } as TransactionData;
};

export const generateMockTransactionData = (
  wallet: Wallet,
  toAddress: string,
  amount: string,
  isNative: boolean = true,
): TransactionData => {
  const fromAddress = wallet.address;

  if (wallet.chain === 'Bitcoin') {
    return generateMockBitcoinTransactionData(fromAddress, toAddress, amount);
  } else {
    return generateMockEthereumTransactionData(fromAddress, toAddress, amount, isNative);
  }
};

export const generateMockTxHash = (chain: string): string => {
  if (chain === 'Bitcoin') {
    return 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6';
  } else {
    return '0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef';
  }
};
