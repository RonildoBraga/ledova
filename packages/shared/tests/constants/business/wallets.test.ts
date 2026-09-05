import {
  EVM_TEST_CHAIN_ID,
  getBlockExplorerTxUrl,
  getWalletVerificationEvmChainId,
  isSupportedEvmTestChainId,
} from '../../../src/constants/business/wallets';

describe('test-network wallet constants', () => {
  it('allows only supported EVM development and test chains', () => {
    expect(isSupportedEvmTestChainId(EVM_TEST_CHAIN_ID.LOCAL)).toBe(true);
    expect(isSupportedEvmTestChainId(EVM_TEST_CHAIN_ID.ETHEREUM_SEPOLIA)).toBe(true);
    expect(isSupportedEvmTestChainId(EVM_TEST_CHAIN_ID.BASE_SEPOLIA)).toBe(true);
    expect(isSupportedEvmTestChainId(1)).toBe(false);
    expect(isSupportedEvmTestChainId(8453)).toBe(false);
  });

  it('maps supported wallet chains to public testnets', () => {
    expect(getWalletVerificationEvmChainId('ethereum')).toBe(EVM_TEST_CHAIN_ID.ETHEREUM_SEPOLIA);
    expect(getWalletVerificationEvmChainId('base')).toBe(EVM_TEST_CHAIN_ID.BASE_SEPOLIA);
    expect(getWalletVerificationEvmChainId('bitcoin')).toBeNull();
  });

  it('uses testnet explorers and has no mainnet fallback', () => {
    expect(getBlockExplorerTxUrl('ethereum', '0x123')).toContain('sepolia.etherscan.io');
    expect(getBlockExplorerTxUrl('base', '0x123')).toContain('sepolia.basescan.org');
    expect(getBlockExplorerTxUrl('bitcoin', 'abc')).toContain('blockstream.info/testnet');
    expect(getBlockExplorerTxUrl('unknown', 'abc')).toBe('');
  });
});
