import { BtcDataType, EthDataType, createBtcSignRequest, createEthSignRequest } from './registry';
import { v4 as uuid } from 'uuid';
import { Transaction } from 'ethers';
import { isSupportedEvmTestChainId } from '@ledova/shared-constants';
import { isBitcoinTestnetSigningPath, isValidBitcoinNativeSegwitTestAddress } from '@ledova/shared-utils';

/**
 * Encode EIP-712 typed data for signing via Keystone hardware wallet.
 * Used for atomic swap signing - signs the swap order hash.
 *
 * Returns cborHex for use with AnimatedQRCode component (for large data that
 * requires multiple QR frames).
 */
export function encodeEthereumTypedData(
  address: string,
  typedData: object,
  derivationPath?: string,
  masterFingerprint?: string,
  chainId?: number,
): { type: string; cbor: Buffer; cborHex: string; urString: string } | null {
  try {
    const requestId = uuid();
    // Convert typed data to JSON string bytes
    const typedDataBytes = Buffer.from(JSON.stringify(typedData), 'utf8');

    if (!derivationPath || !masterFingerprint || chainId === undefined || !isSupportedEvmTestChainId(chainId)) {
      return null;
    }

    const ethSignRequest = createEthSignRequest(
      typedDataBytes,
      EthDataType.typedData,
      derivationPath,
      masterFingerprint,
      requestId,
      chainId,
      address,
      'Ledova',
    );

    const cbor = ethSignRequest.toCBOR();
    const cborHex = cbor.toString('hex');
    const ur = ethSignRequest.toUREncoder(400);
    const urString = ur.nextPart();

    return { type: 'eth-sign-request', cbor, cborHex, urString };
  } catch {
    return null;
  }
}

/**
 * Encode an Ethereum message for signing via Keystone hardware wallet.
 * Used for wallet verification - signs a challenge message.
 */
export function encodeEthereumMessage(
  address: string,
  message: string,
  derivationPath?: string,
  masterFingerprint?: string,
  chainId?: number,
): { type: string; cbor: Buffer; urString: string } | null {
  try {
    const requestId = uuid();
    const messageBytes = Buffer.from(message, 'utf8');

    if (!derivationPath || !masterFingerprint || chainId === undefined || !isSupportedEvmTestChainId(chainId)) {
      return null;
    }

    const ethSignRequest = createEthSignRequest(
      messageBytes,
      EthDataType.personalMessage,
      derivationPath,
      masterFingerprint,
      requestId,
      chainId,
      address,
      'Ledova',
    );

    const cbor = ethSignRequest.toCBOR();
    const ur = ethSignRequest.toUREncoder(400);
    const urString = ur.nextPart();

    return { type: 'eth-sign-request', cbor, urString };
  } catch {
    return null;
  }
}

/**
 * Encode an Ethereum transaction for signing via Keystone hardware wallet.
 * Used for approval transactions and other on-chain transactions.
 *
 * @param transaction - The transaction object (from backend's approval-data endpoint)
 * @param derivationPath - BIP44 derivation path for the signing key
 * @param masterFingerprint - Master fingerprint of the hardware wallet
 * @returns Encoded QR data or null if encoding fails
 */
export function encodeEthereumTransaction(
  transaction: {
    to: string;
    from: string;
    data: string;
    value: string;
    gas: string;
    gasPrice: string;
    nonce: string;
    chainId: string;
  },
  derivationPath?: string,
  masterFingerprint?: string,
): { type: string; cbor: Buffer; cborHex: string; urString: string } | null {
  try {
    const requestId = uuid();

    const chainId = parseInt(transaction.chainId, 16);

    if (!derivationPath || !masterFingerprint || !isSupportedEvmTestChainId(chainId)) {
      return null;
    }

    // Create an unsigned transaction using ethers and serialize it
    const tx = Transaction.from({
      to: transaction.to,
      value: BigInt(transaction.value),
      gasLimit: BigInt(transaction.gas),
      gasPrice: BigInt(transaction.gasPrice),
      nonce: parseInt(transaction.nonce, 16),
      data: transaction.data,
      chainId: chainId,
      type: 0, // Legacy transaction
    });

    // Get the unsigned serialized transaction (RLP-encoded)
    const unsignedTx = tx.unsignedSerialized;
    const txData = Buffer.from(unsignedTx.slice(2), 'hex'); // Remove '0x' prefix

    const ethSignRequest = createEthSignRequest(
      txData,
      EthDataType.transaction,
      derivationPath,
      masterFingerprint,
      requestId,
      chainId,
      transaction.from,
      'Ledova',
    );

    const cbor = ethSignRequest.toCBOR();
    const cborHex = cbor.toString('hex');
    const ur = ethSignRequest.toUREncoder(400);
    const urString = ur.nextPart();

    return { type: 'eth-sign-request', cbor, cborHex, urString };
  } catch (error) {
    console.error('Failed to encode transaction:', error);
    return null;
  }
}

/**
 * Encode a Bitcoin message for signing via Keystone hardware wallet.
 * Used for wallet verification - signs a challenge message.
 */
export function encodeBitcoinMessage(
  address: string,
  message: string,
  derivationPath?: string,
  masterFingerprint?: string,
): { type: string; cbor: Buffer; urString: string } | null {
  try {
    const requestId = uuid();
    const messageBytes = Buffer.from(message, 'utf8');

    if (
      !derivationPath ||
      !masterFingerprint ||
      !isBitcoinTestnetSigningPath(derivationPath) ||
      !isValidBitcoinNativeSegwitTestAddress(address)
    ) {
      return null;
    }

    const btcSignRequest = createBtcSignRequest(
      requestId,
      [masterFingerprint],
      messageBytes,
      BtcDataType.message,
      [derivationPath],
      [address],
      'Ledova',
    );

    const cbor = btcSignRequest.toCBOR();
    const ur = btcSignRequest.toUREncoder(400);
    const urString = ur.nextPart();

    return { type: 'btc-sign-request', cbor, urString };
  } catch {
    return null;
  }
}
