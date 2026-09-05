import { DESIGN_TOKENS } from './design-tokens';

export const getChartColor = (index: number): string =>
  DESIGN_TOKENS.colors.chart[index % DESIGN_TOKENS.colors.chart.length] as string;
