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

      if (networkType === 'BTC') {
        const purposeMatch = accountDerivationPath.match(/^m\/(\d+)'/);
        const purpose = purposeMatch ? parseInt(purposeMatch[1]) : 0;
        if (purpose !== 84) {
          continue;
        }
      }

      const pathComponents = accountDerivationPath.split('/').filter((c) => c && c !== 'm');
      const isAccountLevel = pathComponents.length === 3;

      if (isAccountLevel) {
        const externalChainKey = deriveNonHardenedChild(accountPublicKey, accountChainCode, 0);
        const parentDerivationPath = `${accountDerivationPath}/0`;

        const addressKey = deriveNonHardenedChild(externalChainKey.publicKey, externalChainKey.chainCode, 0);
        const address =
          networkType === 'BTC'
            ? deriveBitcoinAddress(addressKey.publicKey)
            : deriveEthereumAddress(addressKey.publicKey);
        const derivationPath = `${parentDerivationPath}/0`;

        addresses.push({
          address,
          addressIndex: 0,
          derivationPath,
          networkType,
        });

        parentKeys.push({
          parentPublicKey: externalChainKey.publicKey.toString('hex'),
          parentChainCode: externalChainKey.chainCode.toString('hex'),
          parentDerivationPath,
        });
      } else {
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

export function deriveAddressFromParentKey(
  parentPublicKey: string,
  parentChainCode: string,
  parentDerivationPath: string,
  addressIndex: number,
): DerivedAddress {
  const parentPubKeyBuffer = Buffer.from(parentPublicKey, 'hex');
  const parentChainCodeBuffer = Buffer.from(parentChainCode, 'hex');

  const childKey = deriveNonHardenedChild(parentPubKeyBuffer, parentChainCodeBuffer, addressIndex);

  const networkType = detectNetworkFromPath(parentDerivationPath);
  if (networkType === 'UNKNOWN') {
    throw new Error('Unable to detect network type from parent derivation path');
  }

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
