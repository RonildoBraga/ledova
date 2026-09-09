import { useState } from 'react';
import { CaretDownIcon, CaretRightIcon, WalletIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS, formatPercentage, VALUE_SOURCE_LABELS } from '@ledova/shared';
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
  isLoading: boolean;
  hasError: boolean;
  onAssetClick: (assetUuid: string) => void;
}

export function AssetAllocationCard({
  assetAllocation,
  totalValue,
  summary,
  isLoading,
  hasError,
  onAssetClick,
}: AssetAllocationCardProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
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

  if (summary.holdingsCount === 0 && assetAllocation.length === 0) {
    return (
      <Panel>
        <div className="flex flex-col items-center justify-center py-8 gap-2 min-h-[200px]">
          <WalletIcon size={ICON_XL} className="text-text-subtle" />
          <p className="text-sm text-text-muted">No holdings yet</p>
          <p className="text-xs text-text-subtle text-center">Holdings appear here once a wallet holds something</p>
        </div>
      </Panel>
    );
  }

  if (assetAllocation.length === 0) {
    return (
      <Panel>
        <div className="flex flex-col items-center justify-center py-8 gap-2 min-h-[200px]">
          <WalletIcon size={ICON_XL} className="text-text-subtle" />
          <p className="text-sm text-text-muted">Allocation cannot be shown</p>
          <p className="text-xs text-text-subtle text-center">
            {summary.holdingsCount} holding{summary.holdingsCount === 1 ? '' : 's'} could not be weighted
          </p>
        </div>
      </Panel>
    );
  }

  const drawn = assetAllocation.filter((item) => item.percentage > 0);
  const unpricedCount = assetAllocation.filter((item) => item.basis === 'unpriced').length;

  const data = {
    labels: drawn.map((item) => item.symbol),
    datasets: [
      {
        data: drawn.map((item) => item.percentage),
        backgroundColor: drawn.map((item) => item.color),
        borderColor: drawn.map((item) => item.color),
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
          label: (context: { dataIndex: number }) => {
            const item = drawn[context.dataIndex];
            const share = formatPercentage(item.percentage, 1);
            const source = VALUE_SOURCE_LABELS[item.source];
            return item.basis === 'quantity'
              ? `${item.symbol}: ${source} (${share} by quantity)`
              : `${item.symbol}: ${formatDisplayCurrency(item.totalValue)} (${share}; ${source}${item.basis === 'unpriced' ? ', incomplete valuation' : ''})`;
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
              {unpricedCount > 0 && (
                <span className="text-xs text-text-subtle text-center px-4">
                  excludes {unpricedCount} unpriced holding{unpricedCount === 1 ? '' : 's'}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-0.5 px-2">
          {assetAllocation.map((item) => {
            const quantity = item.totalQuantity;
            const hasQuantity = quantity > 0;
            const showQuantity =
              hasQuantity && !(item.totalValue > 0 && Math.abs(quantity / item.totalValue - 1) < 0.05);
            const heldOnSeveralChains = item.perChain.length > 1;
            const isExpanded = expanded === item.assetUuid;

            return (
              <div key={item.assetUuid}>
                <div className="w-full flex items-center gap-2 py-1.5 rounded-lg hover:bg-surface-tertiary/50 transition-colors">
                  {heldOnSeveralChains ? (
                    <button
                      type="button"
                      aria-label={isExpanded ? `Hide ${item.symbol} by chain` : `Show ${item.symbol} by chain`}
                      aria-expanded={isExpanded}
                      onClick={() => setExpanded(isExpanded ? null : item.assetUuid)}
                      className="flex-shrink-0 text-text-muted hover:text-text-primary transition-colors"
                    >
                      {isExpanded ? <CaretDownIcon size={12} /> : <CaretRightIcon size={12} />}
                    </button>
                  ) : (
                    <span className="w-3 flex-shrink-0" />
                  )}

                  <button
                    type="button"
                    onClick={() => onAssetClick(item.assetUuid)}
                    className="flex-1 flex items-center gap-2 text-left"
                  >
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: item.color }} />

                    <div className="flex flex-col">
                      <span className="text-sm font-semibold text-text-primary">{item.name}</span>
                      <span className="text-xs text-text-subtle">{VALUE_SOURCE_LABELS[item.source]}</span>
                      {item.source === 'nav' && item.navPerToken && (
                        <span className="text-xs text-text-subtle">
                          {formatDisplayCurrency(Number(item.navPerToken), 6)} per token
                        </span>
                      )}
                    </div>

                    <div className="flex-1 flex items-baseline justify-end gap-2">
                      {showQuantity && <span className="text-xs text-text-muted">{formatQuantity(quantity)}</span>}
                      <span className="text-xs text-text-muted">
                        {item.basis === 'value' ? formatDisplayCurrency(item.totalValue) : 'unpriced'}
                      </span>
                      <span className="text-sm font-semibold text-text-primary min-w-[36px] text-right">
                        {item.basis === 'unpriced' ? '—' : formatPercentage(item.percentage, 1)}
                      </span>
                    </div>
                  </button>
                </div>

                {heldOnSeveralChains && isExpanded && (
                  <div className="pl-7 pb-1 space-y-0.5">
                    {item.perChain.map((slice) => (
                      <div key={slice.chain} className="flex items-baseline gap-2 text-xs">
                        <span className="text-text-secondary capitalize">{slice.chain || 'unknown chain'}</span>
                        <div className="flex-1 flex items-baseline justify-end gap-2">
                          <span className="text-text-muted">{formatQuantity(slice.quantity)}</span>
                          <span className="text-text-muted min-w-[64px] text-right">
                            {slice.priced ? formatDisplayCurrency(slice.totalValue) : 'unpriced'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </Panel>
  );
}
