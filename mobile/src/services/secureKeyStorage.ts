import * as SecureStore from 'expo-secure-store';
import * as LocalAuthentication from 'expo-local-authentication';
import {
  generateMnemonic as _generateMnemonic,
  validateMnemonic as _validateMnemonic,
} from 'ethereum-cryptography/bip39';
import { wordlist } from 'ethereum-cryptography/bip39/wordlists/english';
import { HDKey } from 'ethereum-cryptography/hdkey';
import { mnemonicToSeedSync } from 'ethereum-cryptography/bip39';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex } from 'ethereum-cryptography/utils';

const SEED_KEY_PREFIX = 'wallet.seed.';
const SEED_SECURED_PREFIX = 'wallet.seed.secured.';

export function generateMnemonic(): string {
  return _generateMnemonic(wordlist, 128);
}

export function validateMnemonic(mnemonic: string): boolean {
  return _validateMnemonic(mnemonic, wordlist);
}

export function computeSeedIdentifier(mnemonic: string): string {
  const seed = mnemonicToSeedSync(mnemonic);
  const masterKey = HDKey.fromMasterSeed(seed);
  const pubKeyHash = sha256(masterKey.publicKey!);
  const identifier = bytesToHex(pubKeyHash).slice(0, 8);
  seed.fill(0);
  masterKey.privateKey?.fill(0);
  return identifier;
}

export async function storeSeedPhrase(seedIdentifier: string, mnemonic: string): Promise<void> {
  await SecureStore.setItemAsync(`${SEED_KEY_PREFIX}${seedIdentifier}`, mnemonic, {
    keychainAccessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
    requireAuthentication: true,
  });
  await SecureStore.setItemAsync(`${SEED_SECURED_PREFIX}${seedIdentifier}`, 'true');
}

export async function getSeedPhrase(seedIdentifier: string): Promise<string | null> {
  const isSecured = await SecureStore.getItemAsync(`${SEED_SECURED_PREFIX}${seedIdentifier}`);

  if (!isSecured) {
    return migrateLegacySeed(seedIdentifier);
  }

  try {
    return await SecureStore.getItemAsync(`${SEED_KEY_PREFIX}${seedIdentifier}`, {
      authenticationPrompt: 'Authenticate to access your wallet',
    });
  } catch {
    return null;
  }
}

async function migrateLegacySeed(seedIdentifier: string): Promise<string | null> {
  const authResult = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Authenticate to access your wallet',
    fallbackLabel: 'Use passcode',
    disableDeviceFallback: false,
  });

  if (!authResult.success) return null;

  const mnemonic = await SecureStore.getItemAsync(`${SEED_KEY_PREFIX}${seedIdentifier}`);
  if (!mnemonic) return null;

  try {
    await SecureStore.setItemAsync(`${SEED_KEY_PREFIX}${seedIdentifier}`, mnemonic, {
      keychainAccessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
      requireAuthentication: true,
    });
    await SecureStore.setItemAsync(`${SEED_SECURED_PREFIX}${seedIdentifier}`, 'true');
  } catch {}

  return mnemonic;
}
