/**
 * UR Signature Decoder for Keystone hardware wallet responses
 */

import { URDecoder } from '@ngraveio/bc-ur';
import { Transaction, Signature } from 'ethers';
import { decodeBtcSignature, decodeEthSignature } from './registry';

/**
 * Decodes a BC-UR signed transaction from Keystone and reconstructs the full signed transaction.
 * Used for approval transactions and other on-chain transactions.
 *
 * @param urSignatureString - The UR signature string from Keystone
 * @param unsignedTx - The original unsigned transaction (for reconstructing with signature)
 * @returns Hex string of the signed transaction ready for broadcast, or null if decoding fails
 */
export function decodeKeystoneSignedTransaction(
  urSignatureString: string,
  unsignedTx?: {
    to: string;
    value: string;
    gas: string;
    gasPrice: string;
    nonce: string;
    data: string;
    chainId: string;
  },
): string | null {
  try {
    const decoder = new URDecoder();
    decoder.receivePart(urSignatureString.toLowerCase());

    if (!decoder.isComplete()) {
      return null;
    }

    const ur = decoder.resultUR();

    if (ur.type === 'eth-signature') {
      const sigBuffer = decodeEthSignature(ur.cbor);

      // Keystone returns 65+ bytes for transaction signatures: r (32) + s (32) + v (1) + optional padding
      // We need at least 65 bytes for a signature, and unsignedTx to reconstruct the full transaction
      // A full RLP-encoded signed transaction would be > 100 bytes, so anything < 100 is treated as signature only
      if (sigBuffer.length >= 65 && sigBuffer.length < 100 && unsignedTx) {
        const r = '0x' + sigBuffer.subarray(0, 32).toString('hex');
        const s = '0x' + sigBuffer.subarray(32, 64).toString('hex');

        // Keystone encodes v differently depending on buffer length:
        // - 65 bytes: v is 1 byte at position 64 (recovery ID: 0 or 1)
        // - 66 bytes: v is 2 bytes at positions 64-65 (big-endian, EIP-155 format)
        let v: number;
        if (sigBuffer.length === 66) {
          // 2-byte big-endian v value (already in EIP-155 format)
          v = (sigBuffer[64] << 8) | sigBuffer[65];
        } else {
          // 1-byte v value (recovery ID)
          const vRaw = sigBuffer[64];

          // Convert recovery ID to EIP-155 format
          const chainId = parseInt(unsignedTx.chainId, 16);
          if (vRaw === 0 || vRaw === 1) {
            v = chainId * 2 + 35 + vRaw;
          } else {
            v = vRaw;
          }
        }

        const chainId = parseInt(unsignedTx.chainId, 16);

        // Create the transaction object
        const txParams = {
          to: unsignedTx.to,
          value: BigInt(unsignedTx.value),
          gasLimit: BigInt(unsignedTx.gas),
          gasPrice: BigInt(unsignedTx.gasPrice),
          nonce: parseInt(unsignedTx.nonce, 16),
          data: unsignedTx.data,
          chainId: chainId,
          type: 0, // Legacy transaction
          signature: Signature.from({ r, s, v }),
        };

        const tx = Transaction.from(txParams);

        return tx.serialized;
      }

      // If >= 100 bytes, assume it's already a full signed transaction (RLP-encoded)
      if (sigBuffer.length >= 100) {
        return '0x' + sigBuffer.toString('hex');
      }
    }

    return null;
  } catch {
    return null;
  }
}

/**
 * Decodes a BC-UR message signature from Keystone for wallet verification.
 * Supports both Ethereum (EIP-191) and Bitcoin message signatures.
 *
 * @param urSignatureString - The UR signature string from Keystone (e.g., "ur:eth-signature/..." or "ur:btc-signature/...")
 * @returns Hex string of the signature (for ETH) or Base64 string (for BTC), or null if decoding fails
 */
export function decodeKeystoneMessageSignature(urSignatureString: string): string | null {
  try {
    const decoder = new URDecoder();
    decoder.receivePart(urSignatureString.toLowerCase());

    if (!decoder.isComplete()) {
      return null;
    }

    const ur = decoder.resultUR();

    if (ur.type === 'eth-signature') {
      const signatureBuffer = decodeEthSignature(ur.cbor);

      if (signatureBuffer.length !== 65) {
        return null;
      }

      // For EIP-191 personal message signing, return the full 65-byte signature as hex with 0x prefix
      return '0x' + signatureBuffer.toString('hex');
    } else if (ur.type === 'btc-signature') {
      const signatureBuffer = decodeBtcSignature(ur.cbor);

      // For Bitcoin, return the signature as base64 (standard format)
      return signatureBuffer.toString('base64');
    } else {
      return null;
    }
  } catch {
    return null;
  }
}
