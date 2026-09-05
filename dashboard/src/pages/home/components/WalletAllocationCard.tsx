import { WalletIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS, formatPercentage, formatCryptoBalance } from '@ledova/shared';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';
import { useCurrency } from '@hooks/useCurrency';
import type { WalletTotals } from '@ledova/shared';
import { Panel } from '@components/Panel';
import { useColors } from '@hooks/useColors';

const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;

ChartJS.register(ArcElement, Tooltip, Legend);

interface WalletAllocationCardProps {
  totals: WalletTotals;
  ethWalletsCount: number;
  btcWalletsCount: number;
  baseWalletsCount: number;
  isLoading: boolean;
}

export function WalletAllocationCard({
  totals,
  ethWalletsCount,
  btcWalletsCount,
  baseWalletsCount,
  isLoading,
}: WalletAllocationCardProps) {
  const { formatDisplayCurrency } = useCurrency();
  const colors = useColors();
  const ETH_COLOR = colors.chain.ethereum;
  const BTC_COLOR = colors.chain.bitcoin;
  const BASE_COLOR = colors.chain.base;
  const TOOLTIP = colors.chartUI.tooltip;

  const totalWallets = ethWalletsCount + btcWalletsCount + baseWalletsCount;
  const totalMarketValue = totals.ethTotalMarketValue + totals.btcTotalMarketValue + totals.baseTotalMarketValue;

  if (isLoading) {
    return (
      <Panel>
        <div className="flex items-center justify-center gap-2 py-6 min-h-[200px]">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-brand-mid"></div>
          <span className="text-sm text-text-muted">Loading wallets...</span>
        </div>
      </Panel>
    );
  }

  if (totalWallets === 0) {
    return (
      <Panel>
        <div className="flex flex-col items-center justify-center py-8 gap-2 min-h-[200px]">
          <WalletIcon size={ICON_XL} className="text-text-subtle" />
          <p className="text-sm text-text-muted">No wallets yet</p>
          <p className="text-xs text-text-subtle text-center">Add wallets to see chain allocation</p>
        </div>
      </Panel>
    );
  }

  const hasEth = totals.ethTotalMarketValue > 0;
  const hasBtc = totals.btcTotalMarketValue > 0;
  const hasBase = totals.baseTotalMarketValue > 0;
  const percentageOf = (value: number) => (totalMarketValue > 0 ? (value / totalMarketValue) * 100 : 0);
  const ethPercentage = percentageOf(totals.ethTotalMarketValue);
  const btcPercentage = percentageOf(totals.btcTotalMarketValue);
  const basePercentage = percentageOf(totals.baseTotalMarketValue);

  const chartEntries = [
    ...(hasEth ? [{ label: 'Ethereum', value: totals.ethTotalMarketValue, color: ETH_COLOR }] : []),
    ...(hasBtc ? [{ label: 'Bitcoin', value: totals.btcTotalMarketValue, color: BTC_COLOR }] : []),
    ...(hasBase ? [{ label: 'Base', value: totals.baseTotalMarketValue, color: BASE_COLOR }] : []),
  ];

  const data = {
    labels: chartEntries.map((e) => e.label),
    datasets: [
      {
        data: chartEntries.map((e) => e.value),
        backgroundColor: chartEntries.map((e) => e.color),
        borderColor: chartEntries.map((e) => e.color),
        borderWidth: 1,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        backgroundColor: TOOLTIP.background,
        titleColor: TOOLTIP.titleColor,
        bodyColor: TOOLTIP.bodyColor,
        borderColor: TOOLTIP.borderColor,
        borderWidth: 1,
        padding: 10,
        callbacks: {
          label: (context: { label: string; parsed: number }) => {
            const value = context.parsed;
            const percentage = ((value / totalMarketValue) * 100).toFixed(1);
            return `${context.label}: ${formatDisplayCurrency(value)} (${percentage}%)`;
          },
        },
      },
    },
    cutout: '65%',
  };

  return (
    <Panel>
      <div className="min-h-[200px]">
        <div className="flex items-center justify-center h-[230px] pt-4">
          <div className="relative w-[220px] h-[220px]">
            <Doughnut data={data} options={options} />
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-base font-bold text-text-primary">{formatDisplayCurrency(totalMarketValue)}</span>
              <span className="text-sm text-text-muted">By Chain</span>
            </div>
          </div>
        </div>

        <div className="space-y-0.5 px-2">
          {hasEth && (
            <div className="flex items-center gap-2 py-1.5">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: ETH_COLOR }} />
              <span className="text-sm font-semibold text-text-primary">Ethereum</span>
              <div className="flex-1 flex items-baseline justify-end gap-2">
                <span className="text-xs text-text-muted">{formatCryptoBalance(totals.eth, '').trimEnd()}</span>
                <span className="text-xs text-text-muted">{formatDisplayCurrency(totals.ethTotalMarketValue)}</span>
                <span className="text-sm font-semibold text-text-primary min-w-[36px] text-right">
                  {formatPercentage(ethPercentage, 1)}
                </span>
              </div>
            </div>
          )}
          {hasBtc && (
            <div className="flex items-center gap-2 py-1.5">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: BTC_COLOR }} />
              <span className="text-sm font-semibold text-text-primary">Bitcoin</span>
              <div className="flex-1 flex items-baseline justify-end gap-2">
                <span className="text-xs text-text-muted">{formatCryptoBalance(totals.btc, '').trimEnd()}</span>
                <span className="text-xs text-text-muted">{formatDisplayCurrency(totals.btcTotalMarketValue)}</span>
                <span className="text-sm font-semibold text-text-primary min-w-[36px] text-right">
                  {formatPercentage(btcPercentage, 1)}
                </span>
              </div>
            </div>
          )}
          {hasBase && (
            <div className="flex items-center gap-2 py-1.5">
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: BASE_COLOR }} />
              <span className="text-sm font-semibold text-text-primary">Base</span>
              <div className="flex-1 flex items-baseline justify-end gap-2">
                <span className="text-xs text-text-muted">{formatCryptoBalance(totals.base, '').trimEnd()}</span>
                <span className="text-xs text-text-muted">{formatDisplayCurrency(totals.baseTotalMarketValue)}</span>
                <span className="text-sm font-semibold text-text-primary min-w-[36px] text-right">
                  {formatPercentage(basePercentage, 1)}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
