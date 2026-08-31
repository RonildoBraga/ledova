import { Buffer } from 'buffer';
import { hmac } from '@noble/hashes/hmac';
import { sha512 } from '@noble/hashes/sha512';
import { sha256 } from '@noble/hashes/sha256';
import { ripemd160 } from '@noble/hashes/ripemd160';
import { secp256k1 } from 'ethereum-cryptography/secp256k1';
import { keccak256 } from 'ethereum-cryptography/keccak';
import { bech32 } from 'bech32';
import type { HardwareWalletNetworkType } from '@ledova/shared-types';

/**
 * Detects network type from BIP44 derivation path
 */
export function detectNetworkFromPath(path: string): HardwareWalletNetworkType | 'UNKNOWN' {
  const match = path.match(/(?:m\/)?(\d+)'\/(\d+)'/);
  if (!match) return 'UNKNOWN';

  const purpose = parseInt(match[1]);
  const coinType = parseInt(match[2]);

  if (purpose === 44 && coinType === 60) return 'ETH';
  if ((purpose === 44 || purpose === 49 || purpose === 84 || purpose === 86) && coinType === 1) return 'BTC';

  return 'UNKNOWN';
}

/**
 * Normalizes derivation path to always start with "m/"
 */
export function normalizeDerivationPath(path: string): string {
  return path.startsWith('m/') ? path : 'm/' + path;
}

/**
 * Derives a child key using non-hardened derivation (BIP32)
 */
export function deriveNonHardenedChild(
  parentPublicKey: Buffer,
  parentChainCode: Buffer,
  index: number,
): { publicKey: Buffer; chainCode: Buffer } {
  if (index >= 0x80000000) {
    throw new Error('Non-hardened derivation requires index < 2^31');
  }

  const compressedParentKey =
    parentPublicKey.length === 33
      ? parentPublicKey
      : Buffer.from(secp256k1.ProjectivePoint.fromHex(parentPublicKey).toRawBytes(true));

  const indexBuffer = Buffer.allocUnsafe(4);
  indexBuffer.writeUInt32BE(index, 0);

  const I = Buffer.from(hmac(sha512, parentChainCode, Buffer.concat([compressedParentKey, indexBuffer])));
  const IL = I.slice(0, 32);
  const childChainCode = I.slice(32);

  const ilBigInt = BigInt('0x' + IL.toString('hex'));
  const parentPoint = secp256k1.ProjectivePoint.fromHex(compressedParentKey);
  const ilPoint = secp256k1.ProjectivePoint.fromPrivateKey(ilBigInt);
  const childPoint = parentPoint.add(ilPoint);

  return {
    publicKey: Buffer.from(childPoint.toRawBytes(true)),
    chainCode: childChainCode,
  };
}

/**
 * Derives an Ethereum address from a public key
 */
export function deriveEthereumAddress(publicKeyBuffer: Buffer): string {
  let publicKeyHex = publicKeyBuffer.toString('hex');

  // Decompress if needed
  if (publicKeyHex.length === 66 && (publicKeyHex.startsWith('02') || publicKeyHex.startsWith('03'))) {
    const point = secp256k1.ProjectivePoint.fromHex(Buffer.from(publicKeyHex, 'hex'));
    publicKeyHex = Buffer.from(point.toRawBytes(false)).toString('hex');
  }

  // Remove '04' prefix for uncompressed keys
  if (publicKeyHex.startsWith('04')) {
    publicKeyHex = publicKeyHex.slice(2);
  }

  const hash = keccak256(Buffer.from(publicKeyHex, 'hex'));
  return '0x' + Buffer.from(hash).slice(-20).toString('hex');
}

/**
 * Derives a Bitcoin testnet Native SegWit (tb1q) address from a public key
 */
export function deriveBitcoinAddress(publicKeyBuffer: Buffer): string {
  const compressedKey =
    publicKeyBuffer.length === 33
      ? publicKeyBuffer
      : Buffer.from(secp256k1.ProjectivePoint.fromHex(publicKeyBuffer).toRawBytes(true));

  const sha256Hash = sha256(compressedKey);
  const hash160 = ripemd160(sha256Hash);

  // BIP84 uses the testnet coin type (1); public-testnet P2WPKH uses the tb HRP.
  const words = bech32.toWords(Buffer.from(hash160));
  return bech32.encode('tb', [0, ...words]);
}
