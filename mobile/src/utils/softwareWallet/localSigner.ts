import { Buffer } from 'buffer';
import { ethers } from 'ethers';
import { HDKey } from 'ethereum-cryptography/hdkey';
import { mnemonicToSeedSync } from 'ethereum-cryptography/bip39';
import { secp256k1 } from 'ethereum-cryptography/secp256k1';
import { sha256 } from '@noble/hashes/sha256';
import { isBitcoinTestnetSigningPath } from '@ledova/shared-utils';

/**
 * Zero out Uint8Arrays to remove sensitive key material from memory.
 *
 * JavaScript strings are immutable and cannot be wiped, so this module works
 * with Uint8Array throughout to minimize private key exposure. The ethers.js
 * SigningKey constructor still creates an internal hex string we can't control,
 * but we eliminate all other copies.
 */
function wipe(...arrays: (Uint8Array | null | undefined)[]): void {
  for (const arr of arrays) {
    if (arr) arr.fill(0);
  }
}

interface DerivedKey {
  privateKey: Uint8Array;
  cleanup: () => void;
}

/**
 * Derive a private key from mnemonic and HD path, wiping all intermediates.
 * Caller MUST call cleanup() when done with the key.
 */
function deriveKey(mnemonic: string, derivationPath: string): DerivedKey {
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

export async function signBitcoinMessage(mnemonic: string, derivationPath: string, message: string): Promise<string> {
  if (!isBitcoinTestnetSigningPath(derivationPath)) {
    throw new Error('Bitcoin signing requires a BIP84 testnet derivation path');
  }

  const seed = mnemonicToSeedSync(mnemonic);
  const masterKey = HDKey.fromMasterSeed(seed);
  const childKey = masterKey.derive(derivationPath);

  if (!childKey.privateKey) {
    wipe(seed, masterKey.privateKey);
    throw new Error('Failed to derive private key from mnemonic');
  }

  try {
    const prefix = '\x18Bitcoin Signed Message:\n';
    const msgBytes = Buffer.from(message, 'utf8');
    const varint = encodeVarint(msgBytes.length);
    const payload = Buffer.concat([Buffer.from(prefix, 'utf8'), varint, msgBytes]);
    const msgHash = sha256(sha256(payload));

    const sig = secp256k1.sign(msgHash, childKey.privateKey);

    // BIP137 header for a compressed native-SegWit P2WPKH address.
    const recoveryFlag = 39 + sig.recovery;
    const rBytes = hexToBytes32(sig.r.toString(16));
    const sBytes = hexToBytes32(sig.s.toString(16));

    const compactSig = Buffer.alloc(65);
    compactSig[0] = recoveryFlag;
    Buffer.from(rBytes).copy(compactSig, 1);
    Buffer.from(sBytes).copy(compactSig, 33);

    return compactSig.toString('base64');
  } finally {
    wipe(seed, masterKey.privateKey, childKey.privateKey);
  }
}

function encodeVarint(n: number): Buffer {
  if (n < 0xfd) return Buffer.from([n]);
  if (n <= 0xffff) {
    const buf = Buffer.alloc(3);
    buf[0] = 0xfd;
    buf.writeUInt16LE(n, 1);
    return buf;
  }
  const buf = Buffer.alloc(5);
  buf[0] = 0xfe;
  buf.writeUInt32LE(n, 1);
  return buf;
}

function hexToBytes32(hex: string): Uint8Array {
  const padded = hex.padStart(64, '0');
  const bytes = new Uint8Array(32);
  for (let i = 0; i < 32; i++) {
    bytes[i] = parseInt(padded.substring(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}
