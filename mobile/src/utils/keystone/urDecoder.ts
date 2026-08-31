/**
 * UR Signature Decoder for Keystone hardware wallet responses
 */

import { URDecoder } from '@ngraveio/bc-ur';
import { ETHSignature } from '@keystonehq/bc-ur-registry-eth';
import { BtcSignature } from '@keystonehq/bc-ur-registry-btc';
import { Transaction } from 'ethers';

/**
 * Decodes a BC-UR signature from Keystone hardware wallet and constructs a signed transaction
 *
 * Supports both Legacy (Type 0) and EIP-1559 (Type 2) transactions.
 *
 * @param urSignatureString - The UR signature string from Keystone (e.g., "ur:eth-signature/...")
 * @param unsignedTransaction - The original unsigned transaction object
 * @returns Hex string of the signed transaction, or null if decoding fails
 */
export function decodeKeystoneSignature(
  urSignatureString: string,
  unsignedTransaction: {
    nonce: number;
    to: string;
    value: number;
    gas: number;
    chainId: number;
    type?: number;
    gasPrice?: number; // Legacy
    maxFeePerGas?: number; // EIP-1559
    maxPriorityFeePerGas?: number; // EIP-1559
    data?: string; // Contract call data (e.g., ERC-20 transfer)
  },
): string | null {
  try {
    // Decode the UR format
    const decoder = new URDecoder();
    decoder.receivePart(urSignatureString.toLowerCase());

    if (!decoder.isComplete()) {
      return null;
    }

    const ur = decoder.resultUR();
    const signature = ETHSignature.fromCBOR(ur.cbor);
    const signatureBuffer = signature.getSignature();

    if (signatureBuffer.length !== 65) {
      return null;
    }

    const r = '0x' + signatureBuffer.slice(0, 32).toString('hex');
    const s = '0x' + signatureBuffer.slice(32, 64).toString('hex');
    const v = signatureBuffer[64];

    // Auto-detect transaction type
    const isEIP1559 =
      unsignedTransaction.type === 2 ||
      (unsignedTransaction.maxFeePerGas !== undefined && unsignedTransaction.maxPriorityFeePerGas !== undefined);

    const ethTx = isEIP1559
      ? Transaction.from({
          type: 2,
          to: unsignedTransaction.to,
          value: unsignedTransaction.value,
          gasLimit: unsignedTransaction.gas,
          maxFeePerGas: unsignedTransaction.maxFeePerGas,
          maxPriorityFeePerGas: unsignedTransaction.maxPriorityFeePerGas,
          nonce: unsignedTransaction.nonce,
          chainId: unsignedTransaction.chainId,
          data: unsignedTransaction.data || '0x',
          signature: { r, s, v },
        })
      : Transaction.from({
          type: 0,
          to: unsignedTransaction.to,
          value: unsignedTransaction.value,
          gasLimit: unsignedTransaction.gas,
          gasPrice: unsignedTransaction.gasPrice,
          nonce: unsignedTransaction.nonce,
          chainId: unsignedTransaction.chainId,
          data: unsignedTransaction.data || '0x',
          signature: { r, s, v },
        });

    return ethTx.serialized;
  } catch {
    return null;
  }
}

/**
 * Decodes a BC-UR message signature from Keystone for wallet verification
 *
 * This is simpler than transaction decoding - just extracts the raw signature.
 * Supports both Ethereum (EIP-191) and Bitcoin message signatures.
 *
 * @param urSignatureString - The UR signature string from Keystone (e.g., "ur:eth-signature/..." or "ur:btc-signature/...")
 * @returns Hex string of the signature (for ETH) or Base64 string (for BTC), or null if decoding fails
 */
export function decodeKeystoneMessageSignature(urSignatureString: string): string | null {
  try {
    // Decode the UR format
    const decoder = new URDecoder();
    decoder.receivePart(urSignatureString.toLowerCase());

    if (!decoder.isComplete()) {
      return null;
    }

    const ur = decoder.resultUR();

    // Check if it's an ETH or BTC signature based on UR type
    if (ur.type === 'eth-signature') {
      const signature = ETHSignature.fromCBOR(ur.cbor);
      const signatureBuffer = signature.getSignature();

      if (signatureBuffer.length !== 65) {
        return null;
      }

      // For EIP-191 personal message signing, return the full 65-byte signature as hex with 0x prefix
      return '0x' + signatureBuffer.toString('hex');
    } else if (ur.type === 'btc-signature') {
      const signature = BtcSignature.fromCBOR(ur.cbor);
      const signatureBuffer = signature.getSignature();

      // For Bitcoin, return the signature as base64 (standard format)
      return signatureBuffer.toString('base64');
    } else {
      return null;
    }
  } catch {
    return null;
  }
}
