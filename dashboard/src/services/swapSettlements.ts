import { Transaction, TypedDataEncoder, getNumber, keccak256, toBeHex, verifyTypedData } from 'ethers';
import { createSwapSettlementStore, type SwapSettlementCrypto, type Wallet } from '@ledova/shared';

type ApprovalTransaction = Awaited<ReturnType<SwapSettlementCrypto['inspectSignedApproval']>>['transaction'];

export function settlementWalletKey(wallet: Wallet | null): string {
  return wallet && typeof wallet.address === 'string'
    ? JSON.stringify([
        wallet.uuid,
        wallet.userAccount,
        wallet.address.toLowerCase(),
        wallet.verificationStatus,
        wallet.chain,
        wallet.signingPreference,
        wallet.derivationPath,
        wallet.masterFingerprint,
        wallet.addressIndex,
        wallet.parentPublicKey,
        wallet.parentChainCode,
        wallet.parentDerivationPath,
      ])
    : '';
}

export const swapSettlementStore = createSwapSettlementStore({
  getAllKeys: () => Object.keys(localStorage),
  getItem: (key) => localStorage.getItem(key),
  setItem: (key, value) => localStorage.setItem(key, value),
  removeItem: (key) => localStorage.removeItem(key),
});

export const swapSettlementCrypto: SwapSettlementCrypto = {
  digestTypedData: (typed) => TypedDataEncoder.hash(typed.domain, { SwapOrder: typed.types.SwapOrder }, typed.message),
  recoverSigner: (typed, signature) =>
    verifyTypedData(typed.domain, { SwapOrder: typed.types.SwapOrder }, typed.message, signature),
  inspectSignedApproval: (raw) => {
    const transaction = Transaction.from(raw);
    if (!transaction.signature || !transaction.from || !transaction.to || transaction.gasPrice === null)
      throw new Error('The signed approval is incomplete.');
    return {
      txHash: keccak256(raw),
      transaction: {
        from: transaction.from,
        to: transaction.to,
        data: transaction.data,
        value: toBeHex(transaction.value),
        gas: toBeHex(transaction.gasLimit),
        gasPrice: toBeHex(transaction.gasPrice),
        nonce: toBeHex(transaction.nonce),
        chainId: toBeHex(transaction.chainId),
      },
    };
  },
};

export function approvalTransactionForSigning(transaction: ApprovalTransaction) {
  return {
    to: transaction.to,
    value: BigInt(transaction.value),
    data: transaction.data,
    gasLimit: BigInt(transaction.gas),
    gasPrice: BigInt(transaction.gasPrice),
    nonce: getNumber(BigInt(transaction.nonce)),
    chainId: BigInt(transaction.chainId),
    type: 0,
  };
}

export function exactSettlementAmount(value: string, decimals: number): string {
  if (!/^(0|[1-9]\d*)$/.test(value) || !Number.isSafeInteger(decimals) || decimals < 0 || decimals > 255)
    throw new Error('The captured amount could not be displayed.');
  if (decimals === 0) return value;
  const padded = value.padStart(decimals + 1, '0');
  return `${padded.slice(0, -decimals)}.${padded.slice(-decimals)}`;
}
