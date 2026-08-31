import { ethers } from 'ethers';
import { HDKey } from 'ethereum-cryptography/hdkey';
import { mnemonicToSeedSync } from 'ethereum-cryptography/bip39';

/**
 * Zero out Uint8Arrays to remove sensitive key material from memory.
 */
function wipe(...arrays: (Uint8Array | null | undefined)[]): void {
  for (const arr of arrays) {
    if (arr) arr.fill(0);
  }
}

/**
 * Derive a private key from mnemonic and HD path, wiping all intermediates.
 * Caller MUST call cleanup() when done with the key.
 */
function deriveKey(mnemonic: string, derivationPath: string) {
  const seed = mnemonicToSeedSync(mnemonic);
  const masterKey = HDKey.fromMasterSeed(seed);
  const childKey = masterKey.derive(derivationPath);

  if (!childKey.privateKey) {
    wipe(seed, masterKey.privateKey);
    throw new Error('Failed to derive private key from mnemonic');
  }

  const privateKey = new Uint8Array(childKey.privateKey);
  wipe(seed, masterKey.privateKey, childKey.privateKey);

  return { privateKey, cleanup: () => wipe(privateKey) };
}

/**
 * Execute a signing operation with a derived Ethereum wallet, ensuring key cleanup.
 */
async function withEthereumSigner<T>(
  mnemonic: string,
  derivationPath: string,
  sign: (wallet: ethers.Wallet) => Promise<T>,
): Promise<T> {
  const { privateKey, cleanup } = deriveKey(mnemonic, derivationPath);
  try {
    const wallet = new ethers.Wallet(new ethers.SigningKey(privateKey));
    return await sign(wallet);
  } finally {
    cleanup();
  }
}

/**
 * Derive the Ethereum address for a mnemonic + derivation path.
 */
export function deriveAddress(mnemonic: string, derivationPath: string): string {
  const { privateKey, cleanup } = deriveKey(mnemonic, derivationPath);
  try {
    const wallet = new ethers.Wallet(new ethers.SigningKey(privateKey));
    return wallet.address;
  } finally {
    cleanup();
  }
}

export async function signEthereumTransaction(
  mnemonic: string,
  derivationPath: string,
  unsignedTx: ethers.TransactionLike,
): Promise<string> {
  return withEthereumSigner(mnemonic, derivationPath, (wallet) => wallet.signTransaction(unsignedTx));
}

export async function signEthereumMessage(mnemonic: string, derivationPath: string, message: string): Promise<string> {
  return withEthereumSigner(mnemonic, derivationPath, (wallet) => wallet.signMessage(message));
}

export async function signEthereumTypedData(
  mnemonic: string,
  derivationPath: string,
  domain: ethers.TypedDataDomain,
  types: Record<string, ethers.TypedDataField[]>,
  value: Record<string, unknown>,
): Promise<string> {
  return withEthereumSigner(mnemonic, derivationPath, (wallet) => wallet.signTypedData(domain, types, value));
}
