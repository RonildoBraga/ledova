import { parseTradingError } from '../../src/services/trading';
import { getEstimatedFee } from '../../src/constants/business/wallets';

describe('parseTradingError allowlist copy', () => {
  it('blames the operator allowlist, not KYC, for a not_whitelisted code', () => {
    const message = parseTradingError({ response: { data: { code: 'not_whitelisted' } } });
    expect(message).toContain('allowlist');
    expect(message).not.toContain('KYC');
  });

  it('blames the operator allowlist for a not-whitelisted detail', () => {
    const message = parseTradingError({ response: { data: { detail: 'Address is not whitelisted.' } } });
    expect(message).toContain('allowlist');
    expect(message).not.toContain('KYC');
  });

  it('blames the operator allowlist on a bare 403', () => {
    const message = parseTradingError({ response: { status: 403 } });
    expect(message).toContain('allowlist');
  });

  it('passes an unrelated detail through untouched', () => {
    expect(parseTradingError({ response: { data: { detail: 'Order has expired.' } } })).toBe('Order has expired.');
  });
});

describe('native transfer fee estimates', () => {
  it('has a Base estimate distinct from the mainnet Ethereum one', () => {
    expect(getEstimatedFee('BASE')).toBeLessThan(getEstimatedFee('ETH'));
  });

  it('still knows Bitcoin and Ethereum', () => {
    expect(getEstimatedFee('BTC')).toBe(0.00005);
    expect(getEstimatedFee('ETH')).toBe(0.0005);
  });

  it('falls back to the Ethereum estimate for an unknown chain', () => {
    expect(getEstimatedFee('DOGE')).toBe(getEstimatedFee('ETH'));
  });
});
