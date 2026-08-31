import { HDKey } from 'ethereum-cryptography/hdkey';
import { sha256 } from 'ethereum-cryptography/sha256';
import { ripemd160 } from 'ethereum-cryptography/ripemd160';
import { keccak256 } from 'ethereum-cryptography/keccak';
import { secp256k1 } from 'ethereum-cryptography/secp256k1';
import { bech32 } from 'bech32';
import { URDecoder } from '@ngraveio/bc-ur';
import { CryptoMultiAccounts } from '@keystonehq/bc-ur-registry';
import type {
  DerivedAddress,
  HardwareWalletNetworkType,
  ParentKeyData,
  HardwareWalletImport,
} from '@ledova/shared-types';

/**
 * Normalizes derivation path to always start with "m/"
 */
function normalizeDerivationPath(path: string): string {
  return path.startsWith('m/') ? path : 'm/' + path;
}

/**
 * Detects network type from BIP44 derivation path
 */
function detectNetworkFromPath(path: string): HardwareWalletNetworkType | 'UNKNOWN' {
  const match = path.match(/(?:m\/)?(\d+)'\/(\d+)'/);
  if (!match) return 'UNKNOWN';

  const purpose = parseInt(match[1]);
  const coinType = parseInt(match[2]);

  if (purpose === 44 && coinType === 60) return 'ETH';
  if ((purpose === 44 || purpose === 49 || purpose === 84 || purpose === 86) && coinType === 1) return 'BTC';

  return 'UNKNOWN';
}

/**
 * Derives an Ethereum address from a public key
 */
function deriveEthereumAddress(publicKey: Uint8Array): string {
  let uncompressedKey: Uint8Array;

  // Decompress if needed
  if (publicKey.length === 33) {
    const point = secp256k1.ProjectivePoint.fromHex(publicKey);
    uncompressedKey = point.toRawBytes(false);
  } else {
    uncompressedKey = publicKey;
  }

  // Remove '04' prefix for uncompressed keys (first byte)
  const keyWithoutPrefix = uncompressedKey.slice(1);

  const hash = keccak256(keyWithoutPrefix);
  return '0x' + Buffer.from(hash.slice(-20)).toString('hex');
}

/**
 * Derives a Bitcoin testnet Native SegWit (tb1q) address from a public key
 */
function deriveBitcoinAddress(publicKey: Uint8Array): string {
  const compressedKey =
    publicKey.length === 33 ? publicKey : secp256k1.ProjectivePoint.fromHex(publicKey).toRawBytes(true);

  const sha256Hash = sha256(compressedKey);
  const hash160 = ripemd160(sha256Hash);

  // BIP84 uses the testnet coin type (1); public-testnet P2WPKH uses the tb HRP.
  const words = bech32.toWords(hash160);
  return bech32.encode('tb', [0, ...words]);
}

/**
 * Derives a new address from stored parent key data
 *
 * @param parentPublicKey - Public key at external chain level (hex string)
 * @param parentChainCode - Chain code at external chain level (hex string)
 * @param parentDerivationPath - Derivation path of parent key (e.g., "m/44'/60'/0'/0")
 * @param addressIndex - Index of the address to derive (0, 1, 2, ...)
 * @returns The derived address information
 */
export function deriveAddressFromParentKey(
  parentPublicKey: string,
  parentChainCode: string,
  parentDerivationPath: string,
  addressIndex: number,
): DerivedAddress {
  // Create an HDKey from the parent public key and chain code
  const parentKey = new HDKey({
    publicKey: Uint8Array.from(Buffer.from(parentPublicKey, 'hex')),
    chainCode: Uint8Array.from(Buffer.from(parentChainCode, 'hex')),
  });

  // Derive child key at the specified index (non-hardened)
  const childKey = parentKey.deriveChild(addressIndex);

  if (!childKey.publicKey) {
    throw new Error('Failed to derive child public key');
  }

  // Determine network type from parent derivation path
  const networkType = detectNetworkFromPath(parentDerivationPath);
  if (networkType === 'UNKNOWN') {
    throw new Error('Unable to detect network type from parent derivation path');
  }

  // Derive the address based on network type
  const address =
    networkType === 'BTC' ? deriveBitcoinAddress(childKey.publicKey) : deriveEthereumAddress(childKey.publicKey);

  const derivationPath = `${parentDerivationPath}/${addressIndex}`;

  return {
    address,
    addressIndex,
    derivationPath,
    networkType,
  };
}

/**
 * Extracts wallet data from a Keystone QR code (crypto-multi-accounts UR type)
 *
 * For account-level keys (e.g., m/44'/60'/0'):
 * - Derives the first address (index 0) for display
 * - Stores the external chain key (m/44'/60'/0'/0) as parent for future derivation
 */
export function extractFromKeystoneQR(urString: string): HardwareWalletImport | null {
  try {
    const decoder = new URDecoder();
    decoder.receivePart(urString.toLowerCase());

    if (!decoder.isComplete()) {
      return null;
    }

    const ur = decoder.resultUR();

    if (ur.type !== 'crypto-multi-accounts') {
      return null;
    }

    const multiAccounts = CryptoMultiAccounts.fromCBOR(ur.cbor);
    const allKeys = multiAccounts.getKeys();
    const masterFingerprint = multiAccounts.getMasterFingerprint().toString('hex');

    const addresses: DerivedAddress[] = [];
    const parentKeys: ParentKeyData[] = [];

    for (let i = 0; i < allKeys.length; i++) {
      const hdKey = allKeys[i];
      const accountPublicKey = hdKey.getKey();
      const accountChainCode = hdKey.getChainCode();
      const originPath = hdKey.getOrigin()?.getPath();

      if (!accountPublicKey || !accountChainCode || !originPath) {
        continue;
      }

      const networkType = detectNetworkFromPath(originPath);
      if (networkType === 'UNKNOWN') {
        continue;
      }

      const accountDerivationPath = normalizeDerivationPath(originPath);

      // For Bitcoin, only accept Native SegWit (m/84') accounts
      if (networkType === 'BTC') {
        const purposeMatch = accountDerivationPath.match(/^m\/(\d+)'/);
        const purpose = purposeMatch ? parseInt(purposeMatch[1]) : 0;
        if (purpose !== 84) {
          continue;
        }
      }

      // Account-level keys have 3 path components: purpose'/coin'/account'
      const pathComponents = accountDerivationPath.split('/').filter((c) => c && c !== 'm');
      const isAccountLevel = pathComponents.length === 3;

      if (isAccountLevel) {
        // Create HDKey from account public key and chain code
        const accountKey = new HDKey({
          publicKey: Uint8Array.from(accountPublicKey),
          chainCode: Uint8Array.from(accountChainCode),
        });

        // Step 1: Derive external chain key (change=0) - this is the parent for address derivation
        const externalChainKey = accountKey.deriveChild(0);
        if (!externalChainKey.publicKey || !externalChainKey.chainCode) {
          continue;
        }
        const parentDerivationPath = `${accountDerivationPath}/0`;

        // Step 2: Derive first address (index=0) from external chain key
        const addressKey = externalChainKey.deriveChild(0);
        if (!addressKey.publicKey) {
          continue;
        }

        const address =
          networkType === 'BTC'
            ? deriveBitcoinAddress(addressKey.publicKey)
            : deriveEthereumAddress(addressKey.publicKey);
        const derivationPath = `${parentDerivationPath}/0`;

        // Store the address for display
        addresses.push({
          address,
          addressIndex: 0,
          derivationPath,
          networkType,
        });

        // Store the parent key (external chain level) for deriving more addresses
        parentKeys.push({
          parentPublicKey: Buffer.from(externalChainKey.publicKey).toString('hex'),
          parentChainCode: Buffer.from(externalChainKey.chainCode).toString('hex'),
          parentDerivationPath,
        });
      } else {
        // Pre-derived address key (5 components) - use as-is
        // This shouldn't happen with Keystone but handle it just in case
        const address =
          networkType === 'BTC'
            ? deriveBitcoinAddress(Uint8Array.from(accountPublicKey))
            : deriveEthereumAddress(Uint8Array.from(accountPublicKey));

        addresses.push({
          address,
          addressIndex: 0,
          derivationPath: accountDerivationPath,
          networkType,
        });
      }
    }

    return {
      addresses,
      masterFingerprint,
      parentKeys,
    };
  } catch {
    return null;
  }
}
