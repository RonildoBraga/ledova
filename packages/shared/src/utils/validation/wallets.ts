const WALLET_ADDRESS_PATTERNS = {
  ETHEREUM: /^0x[a-fA-F0-9]{40}$/,
  BITCOIN_TESTNET_BASE58: /^[mn2][a-km-zA-HJ-NP-Z1-9]{25,34}$/,
  BITCOIN_TESTNET_BECH32: /^tb1[a-z0-9]{39,59}$/,
  BITCOIN_REGTEST_BECH32: /^bcrt1[a-z0-9]{37,59}$/,
} as const;

const isValidEthereumAddress = (address: string): boolean => WALLET_ADDRESS_PATTERNS.ETHEREUM.test(address);

export const isValidNonMainnetBitcoinAddress = (address: string): boolean =>
  WALLET_ADDRESS_PATTERNS.BITCOIN_TESTNET_BASE58.test(address) ||
  WALLET_ADDRESS_PATTERNS.BITCOIN_TESTNET_BECH32.test(address) ||
  WALLET_ADDRESS_PATTERNS.BITCOIN_REGTEST_BECH32.test(address);

/** P2WPKH address family that matches a BIP84 coin-type-1 signing path. */
export const isValidBitcoinNativeSegwitTestAddress = (address: string): boolean =>
  /^tb1q[a-z0-9]{38}$/.test(address) || /^bcrt1q[a-z0-9]{38}$/.test(address);

/** Native-SegWit address-key path on the BIP44 testnet coin type (1). */
export const isBitcoinTestnetSigningPath = (path: string): boolean => /^(?:m\/)?84'\/1'\/\d+'\/[01]\/\d+$/.test(path);

/** Signed raw transaction as `sendrawtransaction` wants it: whitespace and an optional 0x prefix removed, lower-case hex of whole bytes. */
export const normalizeBitcoinRawTransactionHex = (input: string): string | null => {
  const hex = input.replace(/\s+/g, '').replace(/^0x/i, '');
  if (hex.length === 0 || hex.length % 2 !== 0 || !/^[0-9a-fA-F]+$/.test(hex)) return null;
  return hex.toLowerCase();
};

export const validateWalletAddress = (address: string, chainType: string): boolean => {
  const chain = chainType.toLowerCase();
  if (['ethereum', 'eth', 'polygon', 'matic', 'arbitrum', 'optimism', 'base'].includes(chain))
    return isValidEthereumAddress(address);
  if (['bitcoin', 'btc'].includes(chain)) return isValidNonMainnetBitcoinAddress(address);
  return false;
};

export const detectChainFromAddress = (address: string): 'BTC' | 'ETH' | null => {
  if (!address || typeof address !== 'string') return null;
  const trimmed = address.trim();
  if (isValidEthereumAddress(trimmed)) return 'ETH';
  if (isValidNonMainnetBitcoinAddress(trimmed)) return 'BTC';
  return null;
};

const formatWalletAddress = (address: string, maxLength: number = 16): string => {
  if (address.length <= maxLength) return address;
  const prefixLength = Math.floor(maxLength / 2) - 2;
  const suffixLength = maxLength - prefixLength - 3;
  return `${address.slice(0, prefixLength)}...${address.slice(-suffixLength)}`;
};

export const formatWalletAddressShort = (address: string): string => formatWalletAddress(address, 12);
export const formatWalletAddressMedium = (address: string): string => formatWalletAddress(address, 16);
