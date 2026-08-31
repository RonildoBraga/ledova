import { getChainShortCode } from '@ledova/shared-constants';

export interface FormatCurrencyOptions {
  currency?: string;
  locale?: string;
  decimals?: number;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
}

export function formatCurrency(value?: number, options: FormatCurrencyOptions = {}): string {
  if (value === undefined || value === null || isNaN(value)) return '—';
  const {
    currency = 'AUD',
    locale = 'en-AU',
    decimals = 2,
    minimumFractionDigits = decimals,
    maximumFractionDigits = decimals,
  } = options;
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value);
}

export function formatCryptoBalance(balance: string | number, symbol: string, decimals: number = 8): string {
  const balanceNum = typeof balance === 'string' ? parseFloat(balance) : balance;
  if (balanceNum === 0) return `0 ${symbol}`;
  const formatted = balanceNum.toFixed(decimals).replace(/\.?0+$/, '');
  return `${formatted} ${symbol}`;
}

export function getBlockchainShortName(chainName: string): string {
  return getChainShortCode(chainName);
}

export function formatPercentage(value: number, decimals: number = 2): string {
  if (value === undefined || value === null || isNaN(value)) return '—';
  return `${value.toFixed(decimals)}%`;
}

export function formatTokenAmount(rawAmount: string | number, decimals: number): string {
  const raw = typeof rawAmount === 'string' ? parseInt(rawAmount, 10) : rawAmount;
  if (isNaN(raw) || decimals === 0) return raw.toString();
  const divisor = Math.pow(10, decimals);
  return (raw / divisor).toFixed(decimals);
}

export function parseTokenAmount(displayAmount: string, decimals: number): number {
  const parsed = parseFloat(displayAmount);
  if (isNaN(parsed)) return 0;
  const multiplier = Math.pow(10, decimals);
  return Math.round(parsed * multiplier);
}
