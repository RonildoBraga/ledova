import type { JsonValue } from '../types/common';

const SOURCE_OF_FUNDS_LABELS: Record<string, string> = {
  employment_income: 'Employment income',
  savings: 'Savings',
  investment_income: 'Investment income',
  sale_of_assets: 'Sale of assets',
  inheritance: 'Inheritance',
  gift: 'Gift',
  other: 'Other',
};

const INTENDED_USE_LABELS: Record<string, string> = {
  long_term_investment: 'Long-term investment',
  trading_crypto: 'Trading crypto currencies',
  savings: 'Savings',
  other: 'Other',
};

export function sourceOfFundsChoices(funds: JsonValue): string[] {
  return Array.isArray(funds) ? funds.filter((fund): fund is string => typeof fund === 'string') : [];
}

export function formatSourceOfFunds(funds: JsonValue): string {
  return sourceOfFundsChoices(funds)
    .map((fund) => SOURCE_OF_FUNDS_LABELS[fund] || fund)
    .join(', ');
}

export function formatIntendedUse(use: string): string {
  if (!use) return '';
  return INTENDED_USE_LABELS[use] || use;
}
