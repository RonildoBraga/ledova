import { formatCurrency } from '../../src/utils/formatting';

describe('formatCurrency', () => {
  it('should format a number as currency with default options (AUD, 2 decimals)', () => {
    const result = formatCurrency(1234.56);
    expect(result).toBe('$1,234.56');
  });

  it('should format small amounts correctly (prevents $0 bug)', () => {
    const result = formatCurrency(0.29);
    expect(result).toBe('$0.29');
  });

  it('should format with custom decimal places', () => {
    const result = formatCurrency(1234.5678, { decimals: 0 });
    expect(result).toBe('$1,235');
  });

  it('should format with custom currency', () => {
    const result = formatCurrency(1234.56, { currency: 'USD' });

    expect(result).toMatch(/USD.1,234\.56/);
  });

  it('should return dash for undefined value', () => {
    const result = formatCurrency(undefined);
    expect(result).toBe('—');
  });

  it('should return dash for null value', () => {
    const result = formatCurrency(null as unknown as number);
    expect(result).toBe('—');
  });

  it('should return dash for NaN value', () => {
    const result = formatCurrency(NaN);
    expect(result).toBe('—');
  });

  it('should format zero correctly', () => {
    const result = formatCurrency(0);
    expect(result).toBe('$0.00');
  });
});
