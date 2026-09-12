import AsyncStorage from '@react-native-async-storage/async-storage';
import { EthSignRequest, DataType } from '@keystonehq/bc-ur-registry-eth';
import { v4 as uuid } from 'uuid';
import { Transaction, TypedDataEncoder, getNumber, keccak256, toBeHex, verifyTypedData } from 'ethers';
import {
  createSwapSettlementStore,
  hasSwapSettlementContext,
  isSupportedEvmTestChainId,
  selectSwapSettlementLookup,
  type ApprovalTransaction,
  type OrderSubmissionOwner,
  type SwapOrder,
  type SwapSettlementCrypto,
  type Wallet,
} from '@ledova/shared';
import { decodeKeystoneMessageSignature } from '../utils/keystone/urDecoder';

export const swapSettlementStore = createSwapSettlementStore(AsyncStorage);
export const swapSettlementCrypto: SwapSettlementCrypto = {
  digestTypedData: ({ domain, types, message }) =>
    TypedDataEncoder.hash(domain, { SwapOrder: types.SwapOrder }, message),
  recoverSigner: ({ domain, types, message }, signature) =>
    verifyTypedData(domain, { SwapOrder: types.SwapOrder }, message, signature),
  inspectSignedApproval: (raw) => {
    const transaction = Transaction.from(raw);
    if (!transaction.isSigned() || !transaction.from || !transaction.to || transaction.type !== 0)
      throw new Error('The signed approval transaction is unavailable.');
    return {
      txHash: keccak256(raw),
      transaction: {
        from: transaction.from,
        to: transaction.to,
        data: transaction.data,
        value: toBeHex(transaction.value),
        gas: toBeHex(transaction.gasLimit),
        gasPrice: toBeHex(transaction.gasPrice ?? 0n),
        nonce: toBeHex(transaction.nonce),
        chainId: toBeHex(transaction.chainId),
      },
    };
  },
};

export function settlementWalletMaterial(wallet: Wallet | null | undefined): string {
  return JSON.stringify(
    wallet && [
      wallet.uuid,
      wallet.userAccount,
      wallet.address.toLowerCase(),
      wallet.chain,
      wallet.verificationStatus,
      wallet.signingPreference,
      wallet.derivationPath,
      wallet.masterFingerprint,
      wallet.addressIndex,
      wallet.parentPublicKey,
      wallet.parentChainCode,
      wallet.parentDerivationPath,
    ],
  );
}

export function selectMobileSettlement(swap: SwapOrder, owner: OrderSubmissionOwner, wallets: Wallet[]) {
  if (!hasSwapSettlementContext(swap)) throw new Error('This settlement has no valid captured details.');
  const parties = [swap.settlementContext.seller, swap.settlementContext.buyer];
  const unsigned = [!swap.sellerHasSigned, !swap.buyerHasSigned];
  for (const index of [0, 1]) {
    const party = parties[index];
    if (!unsigned[index]) continue;
    const wallet = wallets.find(
      (item) =>
        item.uuid === party.walletUuid &&
        item.userAccount === owner.ownerAccountUuid &&
        item.address.toLowerCase() === party.address.toLowerCase() &&
        item.verificationStatus === 'VERIFIED',
    );
    if (wallet) return { wallet, selection: selectSwapSettlementLookup(swap, owner, wallet, party.orderUuid) };
  }
  throw new Error('No unsigned side has an available wallet in this account.');
}

export function settlementApprovalTransaction(transaction: ApprovalTransaction) {
  return {
    type: 0,
    to: transaction.to,
    value: BigInt(transaction.value),
    gasLimit: BigInt(transaction.gas),
    gasPrice: BigInt(transaction.gasPrice),
    nonce: getNumber(BigInt(transaction.nonce)),
    chainId: BigInt(transaction.chainId),
    data: transaction.data,
  };
}

export function encodeSettlementApproval(
  transaction: ApprovalTransaction,
  wallet: Pick<Wallet, 'address' | 'derivationPath' | 'masterFingerprint'>,
): string {
  const chainId = getNumber(BigInt(transaction.chainId));
  if (!isSupportedEvmTestChainId(chainId) || !wallet.derivationPath || !wallet.masterFingerprint)
    throw new Error('This wallet cannot prepare a signing code.');
  const unsigned = Transaction.from(settlementApprovalTransaction(transaction));
  const request = EthSignRequest.constructETHRequest(
    Buffer.from(unsigned.unsignedSerialized.slice(2), 'hex'),
    DataType.transaction,
    wallet.derivationPath,
    Buffer.from(wallet.masterFingerprint, 'hex') as unknown as string,
    uuid(),
    chainId,
    wallet.address,
    'Ledova',
  );
  return request.toCBOR().toString('hex');
}

export function decodeSettlementApproval(text: string, transaction: ApprovalTransaction): string {
  const signature = decodeKeystoneMessageSignature(text);
  if (!signature || !/^0x[0-9a-f]{130}$/i.test(signature)) throw new Error('The approval signature is invalid.');
  return Transaction.from({ ...settlementApprovalTransaction(transaction), signature }).serialized;
}
