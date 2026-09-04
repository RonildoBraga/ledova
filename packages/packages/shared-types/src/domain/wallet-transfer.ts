import type { Wallet } from './wallet';

export interface PrepareTransferRequest {
  toAddress: string;
  amountEth?: string;
  amountBtc?: string;
  amountToken?: string;
  tokenContract?: string;
}

export interface TransferableAsset {
  uuid: string;
  symbol: string;
  name: string;
  balance: string;
  marketValue: string;
  isNative: boolean;
  contractAddress?: string;
  decimals: number;
  chain: string;
}

export interface PrepareTransferResponse {
  transaction: {
    nonce: number;
    to: string;
    value: number;
    gas: number;
    chainId: number;
    data?: string;
    type?: number;
    gasPrice?: number;
    maxFeePerGas?: number;
    maxPriorityFeePerGas?: number;
  };
  amountEth: string;
  gasPriceWei: string;
  gasPriceGwei: string;
  maxFeePerGasWei?: string;
  maxFeePerGasGwei?: string;
  maxPriorityFeePerGasWei?: string;
  maxPriorityFeePerGasGwei?: string;
  baseFeePerGasWei?: string;
  baseFeePerGasGwei?: string;
  gasLimit: number;
  gasCostEth: string;
  totalCostEth: string;
  fromAddress: string;
  toAddress: string;
}

export interface BroadcastTransferRequest {
  signedTransaction: string;
  toAddress?: string;
  amount?: string;
  transactionFee?: string;
  tokenContract?: string;
}

export interface BroadcastTransferResponse {
  success: boolean;
  txHash: string;
  status: 'pending' | 'confirmed' | 'failed';
  message: string;
  pendingTransaction?: {
    uuid: string;
    txHash: string;
    status: string;
    optimisticHoldingUpdated: boolean;
  } | null;
}

export type TransferStepSimple = 'select-wallet' | 'enter-details' | 'review' | 'sign' | 'broadcast' | 'success';

export interface TransactionData {
  transaction: string;
  fromAddress: string;
  toAddress: string;
  amountEth?: string;
  gasCostEth?: string;
  totalCostEth?: string;
  gasPriceGwei?: string;
  gasLimit?: string;
  amountBtc?: string;
  feeBtc?: string;
  totalCostBtc?: string;
  feePerByte?: string;
  estimatedTxSize?: number;
  amountToken?: string;
  tokenSymbol?: string;
  tokenDecimals?: number;
  tokenContract?: string;
}

export interface TransferState {
  step: TransferStepSimple;
  wallet: Wallet | null;
  selectedAsset: TransferableAsset | null;
  toAddress: string;
  amount: string;
  transactionData: TransactionData | null;
  signedTransaction: string;
  txHash: string;
}
