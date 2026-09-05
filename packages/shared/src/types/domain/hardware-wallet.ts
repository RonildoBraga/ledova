/**
 * Hardware Wallet Types
 *
 * Types for hardware wallet integration (Keystone, Ledger, etc.)
 * Used for QR code-based wallet imports and HD key derivation.
 *
 * HD Wallet Hierarchy:
 * ```
 * m/44'/60'/0'        ← Account Key (what hardware wallet exports)
 *         │
 *         └── /0      ← External Chain Key (parent for deriving addresses)
 *              │
 *              ├── /0 ← Address Index 0 (first address)
 *              ├── /1 ← Address Index 1 (second address)
 *              └── /2 ← Address Index 2 (third address)
 * ```
 */

/**
 * Network type for hardware wallet derivation paths
 */
export type HardwareWalletNetworkType = 'ETH' | 'BTC';

/**
 * A derived address from a hardware wallet
 * Represents a single blockchain address with its derivation info
 */
export interface DerivedAddress {
  /** The blockchain address (0x... for EVM testnets, tb1... for Bitcoin testnet) */
  address: string;
  /** Index of this address in the derivation sequence (0, 1, 2, ...) */
  addressIndex: number;
  /** Full BIP44 derivation path to this address (e.g., "m/44'/60'/0'/0/0") */
  derivationPath: string;
  /** Network type (ETH or BTC) */
  networkType: HardwareWalletNetworkType;
}

/**
 * Parent key data for deriving additional addresses
 * Stored at the "external chain" level (e.g., m/44'/60'/0'/0)
 */
export interface ParentKeyData {
  /** Public key at external chain level (33-byte compressed, hex) */
  parentPublicKey: string;
  /** Chain code at external chain level (32-byte, hex) */
  parentChainCode: string;
  /** Derivation path of the parent key (e.g., "m/44'/60'/0'/0") */
  parentDerivationPath: string;
}

/**
 * Complete hardware wallet import result
 * Contains addresses and parent key data for future derivation
 */
export interface HardwareWalletImport {
  /** Derived addresses from the hardware wallet */
  addresses: DerivedAddress[];
  /** Master fingerprint identifying the hardware wallet (8-char hex) */
  masterFingerprint: string;
  /** Parent key data for deriving additional addresses */
  parentKeys: ParentKeyData[];
}
