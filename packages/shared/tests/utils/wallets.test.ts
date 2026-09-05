import {
  detectChainFromAddress,
  isBitcoinTestnetSigningPath,
  isValidBitcoinNativeSegwitTestAddress,
  isValidNonMainnetBitcoinAddress,
  normalizeBitcoinRawTransactionHex,
  validateWalletAddress,
} from '../../src/utils/validation/wallets';

describe('test-network wallet validation', () => {
  const testnetBase58 = 'mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn';
  const testnetSegwit = `tb1q${'a'.repeat(38)}`;
  const regtestSegwit = `bcrt1q${'a'.repeat(38)}`;

  it.each([testnetBase58, testnetSegwit, regtestSegwit])('accepts a non-mainnet address: %s', (address) => {
    expect(isValidNonMainnetBitcoinAddress(address)).toBe(true);
    expect(validateWalletAddress(address, 'bitcoin')).toBe(true);
    expect(detectChainFromAddress(address)).toBe('BTC');
  });

  it.each(['1BoatSLRHtKNngkdXEeobR76b53LETtpyT', '3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy', `bc1q${'a'.repeat(38)}`])(
    'rejects a mainnet address: %s',
    (address) => {
      expect(isValidNonMainnetBitcoinAddress(address)).toBe(false);
      expect(validateWalletAddress(address, 'bitcoin')).toBe(false);
      expect(detectChainFromAddress(address)).toBeNull();
    },
  );

  it('accepts only BIP84 testnet paths for native-SegWit signing', () => {
    expect(isValidBitcoinNativeSegwitTestAddress(testnetSegwit)).toBe(true);
    expect(isValidBitcoinNativeSegwitTestAddress(regtestSegwit)).toBe(true);
    expect(isBitcoinTestnetSigningPath("m/84'/1'/0'/0/0")).toBe(true);
    expect(isBitcoinTestnetSigningPath("m/84'/0'/0'/0/0")).toBe(false);
  });
});

describe('normalizeBitcoinRawTransactionHex', () => {
  it('strips an optional 0x prefix and whitespace and lower-cases the hex', () => {
    expect(normalizeBitcoinRawTransactionHex('0x0200000001AB')).toBe('0200000001ab');
    expect(normalizeBitcoinRawTransactionHex('  0200 0000\n01ab  ')).toBe('0200000001ab');
  });

  it.each(['', '   ', '0x', '0200000001a', '0200zz', '0x0x02'])(
    'rejects input that is not whole bytes of hex: %j',
    (input) => {
      expect(normalizeBitcoinRawTransactionHex(input)).toBeNull();
    },
  );
});
