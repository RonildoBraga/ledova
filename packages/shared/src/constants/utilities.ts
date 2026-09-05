export type TimeRange = '3M' | '6M' | '1Y' | '2Y' | '3Y' | 'ALL';

export interface TimeRangeConfig {
  label: string;
  value: TimeRange;
  months: number | null;
}

export const TIME_RANGES: TimeRangeConfig[] = [
  { label: '3M', value: '3M', months: 3 },
  { label: '6M', value: '6M', months: 6 },
  { label: '1Y', value: '1Y', months: 12 },
  { label: '2Y', value: '2Y', months: 24 },
  { label: '3Y', value: '3Y', months: 36 },
  { label: 'ALL', value: 'ALL', months: null },
];

export const MAX_CHART_POINTS = 90;

export const PASSWORD_VALIDATION = { MIN_LENGTH: 8 } as const;
export const EMAIL_CONFIRMATION_VALIDATION = { TOKEN_LENGTH: 6 } as const;
