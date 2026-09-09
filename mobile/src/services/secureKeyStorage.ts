import * as SecureStore from 'expo-secure-store';
import * as LocalAuthentication from 'expo-local-authentication';
import { entropyToMnemonic, validateMnemonic as _validateMnemonic } from 'ethereum-cryptography/bip39';
import { wordlist } from 'ethereum-cryptography/bip39/wordlists/english';
import { HDKey } from 'ethereum-cryptography/hdkey';
import { mnemonicToSeedSync } from 'ethereum-cryptography/bip39';
import { sha256 } from '@noble/hashes/sha256';
import { bytesToHex } from 'ethereum-cryptography/utils';
import { getRandomValues } from 'expo-crypto';

const LEGACY_SEED_KEY_PREFIX = 'wallet.seed.';
const SEED_KEY_PREFIX = 'wallet.seed.gated.v2.';
const SEED_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainService: 'ledova.wallet.seeds.v2',
  keychainAccessible: SecureStore.WHEN_PASSCODE_SET_THIS_DEVICE_ONLY,
  requireAuthentication: true,
  authenticationPrompt: 'Authenticate to access your wallet',
};

export function generateMnemonic(): string {
  const entropy = getRandomValues(new Uint8Array(16));
  try {
    return entropyToMnemonic(entropy, wordlist);
  } finally {
    entropy.fill(0);
  }
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
  const key = `${SEED_KEY_PREFIX}${seedIdentifier}`;
  await SecureStore.setItemAsync(key, mnemonic, SEED_OPTIONS);
  if ((await SecureStore.getItemAsync(key, SEED_OPTIONS)) !== mnemonic) {
    throw new Error('Wallet storage did not complete.');
  }
  await removeLegacySeed(seedIdentifier);
}

export async function getSeedPhrase(seedIdentifier: string): Promise<string | null> {
  try {
    const mnemonic = await SecureStore.getItemAsync(`${SEED_KEY_PREFIX}${seedIdentifier}`, SEED_OPTIONS);
    if (!mnemonic) return await migrateLegacySeed(seedIdentifier);
    await removeLegacySeed(seedIdentifier);
    return mnemonic;
  } catch {
    return null;
  }
}

async function removeLegacySeed(seedIdentifier: string): Promise<void> {
  const key = `${LEGACY_SEED_KEY_PREFIX}${seedIdentifier}`;
  await SecureStore.deleteItemAsync(key);
  if (await SecureStore.getItemAsync(key, { authenticationPrompt: SEED_OPTIONS.authenticationPrompt })) {
    throw new Error('Legacy wallet removal did not complete.');
  }
  await SecureStore.deleteItemAsync(`wallet.seed.secured.${seedIdentifier}`);
}

async function migrateLegacySeed(seedIdentifier: string): Promise<string | null> {
  const authResult = await LocalAuthentication.authenticateAsync({
    promptMessage: 'Authenticate to access your wallet',
    fallbackLabel: 'Use passcode',
    disableDeviceFallback: false,
  });

  if (!authResult.success) return null;

  const mnemonic = await SecureStore.getItemAsync(`${LEGACY_SEED_KEY_PREFIX}${seedIdentifier}`, {
    authenticationPrompt: SEED_OPTIONS.authenticationPrompt,
  });
  if (!mnemonic) return null;

  try {
    await storeSeedPhrase(seedIdentifier, mnemonic);
  } catch {
    return null;
  }

  return mnemonic;
}
