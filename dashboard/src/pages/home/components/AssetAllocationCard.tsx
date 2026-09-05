import { WalletIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS, formatPercentage } from '@ledova/shared';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';
import { useCurrency } from '@hooks/useCurrency';
import type { AssetAllocationItem, HoldingsSummary } from '@ledova/shared';
import { Panel } from '@components/Panel';
import { useColors } from '@hooks/useColors';

const ICON_XL = DESIGN_TOKENS.icon.sizes.xl;

ChartJS.register(ArcElement, Tooltip, Legend);

interface AssetAllocationCardProps {
  assetAllocation: AssetAllocationItem[];
  totalValue: number;
  summary: HoldingsSummary;
  assetQuantities: Record<string, number>;
  isLoading: boolean;
  hasError: boolean;
  onAssetClick: (assetUuid: string) => void;
}

export function AssetAllocationCard({
  assetAllocation,
  totalValue,
  summary,
  assetQuantities,
  isLoading,
  hasError,
  onAssetClick,
}: AssetAllocationCardProps) {
  const { formatDisplayCurrency } = useCurrency();
  const colors = useColors();
  const TOOLTIP = colors.chartUI.tooltip;

  const formatQuantity = (quantity: number) => {
    return quantity.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 6,
    });
  };

  if (isLoading) {
    return (
      <Panel>
        <div className="flex items-center justify-center gap-2 py-6 min-h-[200px]">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-brand-mid"></div>
          <span className="text-sm text-text-muted">Loading allocation...</span>
        </div>
      </Panel>
    );
  }

  if (hasError) {
    return (
      <Panel>
        <div className="flex items-center justify-center py-6 min-h-[200px]">
          <span className="text-sm text-error-light">Failed to load holdings</span>
        </div>
      </Panel>
    );
  }

  if (summary.holdingsCount === 0 || assetAllocation.length === 0) {
    return (
      <Panel>
        <div className="flex flex-col items-center justify-center py-8 gap-2 min-h-[200px]">
          <WalletIcon size={ICON_XL} className="text-text-subtle" />
          <p className="text-sm text-text-muted">No holdings yet</p>
          <p className="text-xs text-text-subtle text-center">Add wallets to see allocation</p>
        </div>
      </Panel>
    );
  }

  const data = {
    labels: assetAllocation.map((item) => item.symbol),
    datasets: [
      {
        data: assetAllocation.map((item) => item.totalValue),
        backgroundColor: assetAllocation.map((item) => item.color),
        borderColor: assetAllocation.map((item) => item.color),
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
            const percentage = ((value / totalValue) * 100).toFixed(1);
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
              <span className="text-base font-bold text-text-primary">{formatDisplayCurrency(totalValue)}</span>
              <span className="text-sm text-text-muted">Total</span>
            </div>
          </div>
        </div>

        <div className="space-y-0.5 px-2">
          {assetAllocation.map((item) => {
            const quantity = assetQuantities[item.symbol];
            const hasQuantity = quantity !== undefined && quantity > 0;
            const showQuantity =
              hasQuantity && !(item.totalValue > 0 && Math.abs(quantity / item.totalValue - 1) < 0.05);

            return (
              <button
                key={item.assetUuid}
                type="button"
                onClick={() => onAssetClick(item.assetUuid)}
                className="w-full flex items-center gap-2 py-1.5 rounded-lg hover:bg-surface-tertiary/50 transition-colors text-left"
              >
                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />

                <div className="flex flex-col">
                  <span className="text-sm font-semibold text-text-primary">{item.name}</span>
                  {item.isYieldToken && item.navPerToken && (
                    <span className="text-xs text-text-subtle">NAV: ${parseFloat(item.navPerToken).toFixed(6)}</span>
                  )}
                </div>

                <div className="flex-1 flex items-baseline justify-end gap-2">
                  {showQuantity && <span className="text-xs text-text-muted">{formatQuantity(quantity)}</span>}
                  <span className="text-xs text-text-muted">{formatDisplayCurrency(item.totalValue)}</span>
                  <span className="text-sm font-semibold text-text-primary min-w-[36px] text-right">
                    {formatPercentage(item.percentage, 1)}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </Panel>
  );
}
