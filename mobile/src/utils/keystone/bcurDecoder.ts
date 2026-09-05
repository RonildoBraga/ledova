import { URDecoder } from '@ngraveio/bc-ur';
import { CryptoMultiAccounts } from '@keystonehq/bc-ur-registry';
import { Buffer } from 'buffer';
import type { DerivedAddress, ParentKeyData, HardwareWalletImport, HardwareWalletNetworkType } from '@ledova/shared';
import {
  detectNetworkFromPath,
  normalizeDerivationPath,
  deriveNonHardenedChild,
  deriveEthereumAddress,
  deriveBitcoinAddress,
} from '../crypto/bip32';

export type { DerivedAddress, ParentKeyData, HardwareWalletImport, HardwareWalletNetworkType };

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
        // Step 1: Derive external chain key (change=0) - this is the parent for address derivation
        const externalChainKey = deriveNonHardenedChild(accountPublicKey, accountChainCode, 0);
        const parentDerivationPath = `${accountDerivationPath}/0`;

        // Step 2: Derive first address (index=0) from external chain key
        const addressKey = deriveNonHardenedChild(externalChainKey.publicKey, externalChainKey.chainCode, 0);
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
          parentPublicKey: externalChainKey.publicKey.toString('hex'),
          parentChainCode: externalChainKey.chainCode.toString('hex'),
          parentDerivationPath,
        });
      } else {
        // Pre-derived address key (5 components) - use as-is
        // This shouldn't happen with Keystone but handle it just in case
        const address =
          networkType === 'BTC' ? deriveBitcoinAddress(accountPublicKey) : deriveEthereumAddress(accountPublicKey);

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
  const parentPubKeyBuffer = Buffer.from(parentPublicKey, 'hex');
  const parentChainCodeBuffer = Buffer.from(parentChainCode, 'hex');

  // Derive child key at the specified index
  const childKey = deriveNonHardenedChild(parentPubKeyBuffer, parentChainCodeBuffer, addressIndex);

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
