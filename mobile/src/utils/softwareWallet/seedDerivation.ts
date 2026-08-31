import { Buffer } from 'buffer';
import { HDKey } from 'ethereum-cryptography/hdkey';
import { mnemonicToSeedSync } from 'ethereum-cryptography/bip39';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex } from 'ethereum-cryptography/utils';
import type { DerivedAddress, ParentKeyData } from '@ledova/shared-types';
import { deriveNonHardenedChild, deriveEthereumAddress, deriveBitcoinAddress } from '../crypto/bip32';

export interface SoftwareWalletImport {
  addresses: DerivedAddress[];
  masterFingerprint: string;
  parentKeys: ParentKeyData[];
}

/**
 * Derive ETH and BTC addresses from a mnemonic.
 * Returns the same structure as HardwareWalletImport for compatibility.
 */
export function deriveAccountsFromMnemonic(mnemonic: string): SoftwareWalletImport {
  const seed = mnemonicToSeedSync(mnemonic);
  const masterKey = HDKey.fromMasterSeed(seed);

  // Master fingerprint: first 4 bytes (8 hex chars) of hash of master public key
  const masterPubHash = sha256(masterKey.publicKey!);
  const masterFingerprint = bytesToHex(masterPubHash).slice(0, 8);

  const addresses: DerivedAddress[] = [];
  const parentKeys: ParentKeyData[] = [];

  // --- ETH: m/44'/60'/0' ---
  const ethAccount = masterKey.derive("m/44'/60'/0'");
  // External chain key: m/44'/60'/0'/0
  const ethExternal = ethAccount.deriveChild(0);
  const ethParentPath = "m/44'/60'/0'/0";

  const ethExternalPubKey = Buffer.from(ethExternal.publicKey!);
  const ethExternalChainCode = Buffer.from(ethExternal.chainCode!);

  // First address: m/44'/60'/0'/0/0
  const ethAddressKey = deriveNonHardenedChild(ethExternalPubKey, ethExternalChainCode, 0);
  const ethAddress = deriveEthereumAddress(ethAddressKey.publicKey);

  addresses.push({
    address: ethAddress,
    addressIndex: 0,
    derivationPath: `${ethParentPath}/0`,
    networkType: 'ETH',
  });

  parentKeys.push({
    parentPublicKey: ethExternalPubKey.toString('hex'),
    parentChainCode: ethExternalChainCode.toString('hex'),
    parentDerivationPath: ethParentPath,
  });

  // --- BTC testnet: m/84'/1'/0' (Native SegWit) ---
  const btcAccount = masterKey.derive("m/84'/1'/0'");
  // External chain key: m/84'/1'/0'/0
  const btcExternal = btcAccount.deriveChild(0);
  const btcParentPath = "m/84'/1'/0'/0";

  const btcExternalPubKey = Buffer.from(btcExternal.publicKey!);
  const btcExternalChainCode = Buffer.from(btcExternal.chainCode!);

  // First address: m/84'/1'/0'/0/0
  const btcAddressKey = deriveNonHardenedChild(btcExternalPubKey, btcExternalChainCode, 0);
  const btcAddress = deriveBitcoinAddress(btcAddressKey.publicKey);

  addresses.push({
    address: btcAddress,
    addressIndex: 0,
    derivationPath: `${btcParentPath}/0`,
    networkType: 'BTC',
  });

  parentKeys.push({
    parentPublicKey: btcExternalPubKey.toString('hex'),
    parentChainCode: btcExternalChainCode.toString('hex'),
    parentDerivationPath: btcParentPath,
  });

  // Wipe sensitive key material from memory
  seed.fill(0);
  masterKey.privateKey?.fill(0);
  ethAccount.privateKey?.fill(0);
  ethExternal.privateKey?.fill(0);
  btcAccount.privateKey?.fill(0);
  btcExternal.privateKey?.fill(0);

  return {
    addresses,
    masterFingerprint,
    parentKeys,
  };
}
