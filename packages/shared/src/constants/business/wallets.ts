export const WALLET_VERIFICATION_STATUS = {
  PENDING: 'PENDING',
  VERIFIED: 'VERIFIED',
} as const;

export const WALLET_TYPE = {
  HARDWARE: 'hardware',
  SOFTWARE: 'software',
} as const;

export const BLOCKCHAIN = {
  ETHEREUM: 'ethereum',
  BITCOIN: 'bitcoin',
  BASE: 'base',
  POLYGON: 'polygon',
  SOLANA: 'solana',
  AVALANCHE: 'avalanche',
} as const;

export type BlockchainType = (typeof BLOCKCHAIN)[keyof typeof BLOCKCHAIN];

export const EVM_TEST_CHAIN_ID = {
  ETHEREUM_SEPOLIA: 11155111,
  BASE_SEPOLIA: 84532,
  LOCAL: 31337,
} as const;

const supportedEvmTestChainIds = new Set<number>(Object.values(EVM_TEST_CHAIN_ID));

export function isSupportedEvmTestChainId(chainId: number): boolean {
  return Number.isInteger(chainId) && supportedEvmTestChainIds.has(chainId);
}

export function getWalletVerificationEvmChainId(chain: string): number | null {
  const normalized = chain.trim().toLowerCase();
  if (normalized === BLOCKCHAIN.ETHEREUM || normalized === 'eth') return EVM_TEST_CHAIN_ID.ETHEREUM_SEPOLIA;
  if (normalized === BLOCKCHAIN.BASE) return EVM_TEST_CHAIN_ID.BASE_SEPOLIA;
  return null;
}

export interface ChainConfig {
  code: BlockchainType;
  name: string;
  shortName: string;
  isActive: boolean;
  explorerTxUrl: string;
  explorerAddressUrl: string;
  addressPlaceholder: string;
  confirmationTime: string;
}

export const SUPPORTED_CHAINS: ChainConfig[] = [
  {
    code: BLOCKCHAIN.ETHEREUM,
    name: 'Ethereum',
    shortName: 'ETH',
    isActive: true,
    explorerTxUrl: 'https://sepolia.etherscan.io/tx/',
    explorerAddressUrl: 'https://sepolia.etherscan.io/address/',
    addressPlaceholder: '0x...',
    confirmationTime: '~2-3 minutes',
  },
  {
    code: BLOCKCHAIN.BITCOIN,
    name: 'Bitcoin',
    shortName: 'BTC',
    isActive: true,
    explorerTxUrl: 'https://blockstream.info/testnet/tx/',
    explorerAddressUrl: 'https://blockstream.info/testnet/address/',
    addressPlaceholder: 'm..., n..., 2..., tb1... or bcrt1...',
    confirmationTime: '~10 minutes',
  },
  {
    code: BLOCKCHAIN.BASE,
    name: 'Base',
    shortName: 'BASE',
    isActive: true,
    explorerTxUrl: 'https://sepolia.basescan.org/tx/',
    explorerAddressUrl: 'https://sepolia.basescan.org/address/',
    addressPlaceholder: '0x...',
    confirmationTime: '~2 seconds',
  },
  {
    code: BLOCKCHAIN.POLYGON,
    name: 'Polygon',
    shortName: 'MATIC',
    isActive: false,
    explorerTxUrl: '',
    explorerAddressUrl: '',
    addressPlaceholder: '0x...',
    confirmationTime: '~2 minutes',
  },
  {
    code: BLOCKCHAIN.SOLANA,
    name: 'Solana',
    shortName: 'SOL',
    isActive: false,
    explorerTxUrl: '',
    explorerAddressUrl: '',
    addressPlaceholder: 'Enter address',
    confirmationTime: '~1 minute',
  },
  {
    code: BLOCKCHAIN.AVALANCHE,
    name: 'Avalanche',
    shortName: 'AVAX',
    isActive: false,
    explorerTxUrl: '',
    explorerAddressUrl: '',
    addressPlaceholder: '0x...',
    confirmationTime: '~2 minutes',
  },
];

const chainByCode = new Map(SUPPORTED_CHAINS.map((c) => [c.code, c]));
const chainByShortName = new Map(SUPPORTED_CHAINS.map((c) => [c.shortName, c]));

export function getChainConfig(code: string): ChainConfig | undefined {
  return chainByCode.get(code as BlockchainType);
}

export function getChainByShortName(shortName: string): ChainConfig | undefined {
  return chainByShortName.get(shortName);
}

export function getActiveChains(): ChainConfig[] {
  return SUPPORTED_CHAINS.filter((c) => c.isActive);
}

export function getChainName(chain: string): string {
  const normalized = chain?.toLowerCase() || '';
  if (chainByCode.has(normalized as BlockchainType)) return normalized;
  const config = chainByShortName.get(chain?.toUpperCase() || '');
  return config?.code || normalized;
}

export function getChainShortCode(chain: string): string {
  const normalized = chain?.toLowerCase() || '';
  const config = chainByCode.get(normalized as BlockchainType);
  if (config) return config.shortName;
  const aliases: Record<string, string> = { btc: 'BTC', eth: 'ETH', sol: 'SOL', avax: 'AVAX' };
  if (aliases[normalized]) return aliases[normalized];
  const upper = chain?.toUpperCase() || '';
  return chainByShortName.has(upper) ? upper : upper;
}

export function isEthereumChain(chainShortCode: string): boolean {
  return chainShortCode === 'ETH';
}

export function isBitcoinChain(chainShortCode: string): boolean {
  return chainShortCode === 'BTC';
}

export function getBlockchainDisplayName(chainShortCode: string): string {
  return chainByShortName.get(chainShortCode)?.name || chainShortCode;
}

export function getAddressPlaceholder(chainShortCode: string): string {
  return chainByShortName.get(chainShortCode)?.addressPlaceholder || 'Enter address';
}

function resolveChainConfig(chain: string): ChainConfig | undefined {
  const normalized = chain?.toLowerCase() || '';
  const config = chainByCode.get(normalized as BlockchainType);
  if (config) return config;
  const aliases: Record<string, BlockchainType> = { btc: BLOCKCHAIN.BITCOIN, eth: BLOCKCHAIN.ETHEREUM };
  return aliases[normalized] ? chainByCode.get(aliases[normalized]) : undefined;
}

export function getBlockExplorerTxUrl(chain: string, txHash: string): string {
  const config = resolveChainConfig(chain);
  return config?.explorerTxUrl ? `${config.explorerTxUrl}${txHash}` : '';
}

export function getBlockExplorerAddressUrl(chain: string, address: string): string {
  const config = resolveChainConfig(chain);
  return config?.explorerAddressUrl ? `${config.explorerAddressUrl}${address}` : '';
}

export interface BuyableAssetConfig {
  symbol: string;
  name: string;
  chain: BlockchainType;
}

export const BUYABLE_ASSETS: BuyableAssetConfig[] = [
  { symbol: 'BTC', name: 'Bitcoin', chain: BLOCKCHAIN.BITCOIN },
  { symbol: 'ETH', name: 'Ethereum', chain: BLOCKCHAIN.ETHEREUM },
  { symbol: 'USDC', name: 'USD Coin', chain: BLOCKCHAIN.ETHEREUM },
  { symbol: 'USDT', name: 'Tether', chain: BLOCKCHAIN.ETHEREUM },
];

const TRANSFER_FEE_ESTIMATES = { BTC: 0.00005, ETH: 0.0005 } as const;

export function getEstimatedFee(chainShortName: string): number {
  return TRANSFER_FEE_ESTIMATES[chainShortName as keyof typeof TRANSFER_FEE_ESTIMATES] || TRANSFER_FEE_ESTIMATES.ETH;
}
