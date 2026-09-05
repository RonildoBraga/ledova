import { useState, useCallback, useMemo } from 'react';
import type { Asset } from '@ledova/shared';
import { TIME_RANGES } from '@ledova/shared';
import { useCurrency } from '@hooks/useCurrency';
import { StarIcon } from '@phosphor-icons/react';
import { AssetTypeIcon } from '@components/AssetTypeIcon';
import { useColors } from '@hooks/useColors';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  type Plugin,
  type ChartEvent,
  type ActiveElement,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { Modal } from '@components/Modal';
import { useAssetPriceHistory } from '../useAssetPrices';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

interface AssetDetailModalProps {
  isOpen: boolean;
  asset: Asset | null;
  onClose: () => void;
  onBuy?: () => void;
  isFavourite?: boolean;
  onToggleFavourite?: (assetUuid: string) => void;
}

export function AssetDetailModal({
  isOpen,
  asset,
  onClose,
  onBuy,
  isFavourite = false,
  onToggleFavourite,
}: AssetDetailModalProps) {
  const { formatDisplayCurrency } = useCurrency();
  const colors = useColors();
  const CHART_UI = colors.chartUI;

  const { chartData, periodChangePercent, selectedTimeRange, setSelectedTimeRange, isLoading, error } =
    useAssetPriceHistory(asset?.uuid || null);

  const [activePointIndex, setActivePointIndex] = useState<number | null>(null);

  const handleChartHover = useCallback((_event: ChartEvent, elements: ActiveElement[]) => {
    if (elements.length > 0) {
      setActivePointIndex(elements[0].index);
    }
  }, []);

  const handleChartMouseLeave = useCallback(() => {
    setActivePointIndex(null);
  }, []);

  const isPositiveOverall = periodChangePercent !== null ? periodChangePercent >= 0 : true;
  const lineColor = isPositiveOverall ? colors.success.default : colors.error.default;

  const lineChartData = useMemo(() => {
    if (!chartData || chartData.length === 0) return null;

    return {
      labels: chartData.map((point) => {
        const date = new Date(point.date);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
      }),
      datasets: [
        {
          label: 'Price',
          data: chartData.map((point) => point.price),
          borderColor: lineColor,
          backgroundColor: `${lineColor}20`,
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 6,
          pointHoverBackgroundColor: lineColor,
          pointHoverBorderColor: lineColor,
          pointBackgroundColor: lineColor,
        },
      ],
    };
  }, [chartData, lineColor]);

  const crosshairPlugin: Plugin<'line'> = useMemo(
    () => ({
      id: 'crosshair',
      beforeDraw(chart) {
        if (activePointIndex === null) return;

        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data[activePointIndex]) return;

        const x = meta.data[activePointIndex].x;
        const { ctx, chartArea } = chart;

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.lineWidth = 1;
        ctx.strokeStyle = CHART_UI.tickColor;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.restore();
      },
    }),
    [activePointIndex],
  );

  const chartOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      onHover: handleChartHover,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
      scales: {
        x: {
          display: false,
        },
        y: {
          display: false,
        },
      },
      interaction: {
        mode: 'index' as const,
        intersect: false,
      },
    }),
    [handleChartHover],
  );

  if (!asset) return null;

  const activePoint = activePointIndex != null ? chartData?.[activePointIndex] : null;
  const isScrubbing = activePoint != null;

  const displayPrice = isScrubbing ? activePoint.price : asset.currentPrice ? parseFloat(asset.currentPrice) : null;

  const displayChangePercent = isScrubbing ? activePoint.changePercent : periodChangePercent;
  const isPositiveChange = displayChangePercent !== null ? displayChangePercent >= 0 : true;

  const scrubbedDateLabel = isScrubbing
    ? (() => {
        try {
          const date = new Date(activePoint.date);
          if (isNaN(date.getTime())) return '';
          return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch {
          return '';
        }
      })()
    : null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      showFooter={!!onBuy}
      showCancelButton
      cancelLabel="Close"
      confirmLabel="Buy"
      onCancel={onClose}
      onConfirm={onBuy}
    >
      <div className="relative flex items-center justify-center mb-4">
        <div className="flex flex-col items-center gap-1">
          <AssetTypeIcon assetType={asset.assetType} symbol={asset.symbol} size={32} />
          <h3 className="text-sm font-medium text-text-muted">{asset.name}</h3>
        </div>
        {onToggleFavourite && (
          <button
            type="button"
            onClick={() => onToggleFavourite(asset.uuid)}
            className="absolute right-0 top-0 p-1 transition-colors"
          >
            <StarIcon
              size={20}
              color={isFavourite ? colors.status.warning.icon : colors.text.subtle}
              weight={isFavourite ? 'fill' : 'regular'}
            />
          </button>
        )}
      </div>

      <div className="flex flex-col items-center mb-4">
        <span className="text-2xl font-bold text-text-primary">
          {displayPrice !== null ? formatDisplayCurrency(displayPrice, asset.isYieldToken ? 6 : undefined) : 'N/A'}
        </span>
        {displayChangePercent !== null && (
          <span
            className={`mt-1 px-2 py-0.5 rounded-full text-sm font-semibold ${
              isPositiveChange ? 'bg-success-light/20 text-success-light' : 'bg-error-light/20 text-error-light'
            }`}
          >
            {isPositiveChange ? '+' : ''}
            {displayChangePercent.toFixed(2)}%
          </span>
        )}
        {scrubbedDateLabel && <span className="mt-1 text-xs text-text-muted">{scrubbedDateLabel}</span>}
      </div>

      <div className="h-[220px] rounded-lg overflow-hidden" onMouseLeave={handleChartMouseLeave}>
        {isLoading ? (
          <div className="h-full flex flex-col items-center justify-center gap-2">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-brand-mid"></div>
            <span className="text-sm text-text-muted">Loading chart...</span>
          </div>
        ) : error ? (
          <div className="h-full flex items-center justify-center">
            <span className="text-sm text-error-light">Failed to load price history</span>
          </div>
        ) : chartData.length === 0 || !lineChartData ? (
          <div className="h-full flex items-center justify-center">
            <span className="text-sm text-text-muted">No price data available</span>
          </div>
        ) : (
          <div className="h-full p-3">
            <Line data={lineChartData} options={chartOptions} plugins={[crosshairPlugin]} />
          </div>
        )}
      </div>

      <div className="flex justify-center mt-4 mb-2">
        <div className="inline-flex bg-surface-tertiary rounded-full p-0.5">
          {TIME_RANGES.map((range) => (
            <button
              key={range.value}
              type="button"
              onClick={() => setSelectedTimeRange(range.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                selectedTimeRange === range.value
                  ? 'bg-brand-light text-white font-semibold'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {range.label}
            </button>
          ))}
        </div>
      </div>

      {chartData.length > 0 && (
        <div className="mt-4 flex justify-between text-xs text-text-subtle">
          <span>
            Low: {formatDisplayCurrency(Math.min(...chartData.map((p) => p.price)), asset.isYieldToken ? 6 : undefined)}
          </span>
          <span>
            High:{' '}
            {formatDisplayCurrency(Math.max(...chartData.map((p) => p.price)), asset.isYieldToken ? 6 : undefined)}
          </span>
        </div>
      )}

      {asset.isYieldToken && asset.navPerToken && (
        <div className="mt-4 pt-3 border-t border-surface-border">
          <div className="flex justify-between items-center text-sm">
            <span className="text-text-muted">NAV per Token</span>
            <span className="font-semibold text-text-primary">
              {formatDisplayCurrency(parseFloat(asset.navPerToken), 6)}
            </span>
          </div>
          {asset.lastNavUpdate && (
            <div className="flex justify-between items-center text-sm mt-1">
              <span className="text-text-muted">Last NAV Update</span>
              <span className="text-text-secondary">
                {new Date(asset.lastNavUpdate).toLocaleDateString('en-AU', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
