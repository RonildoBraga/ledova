import { useCallback, useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  type Plugin,
  type ChartEvent,
  type ActiveElement,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { useColors } from '@hooks/useColors';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

interface HoldingsChartProps {
  instrumentData: {
    data: Record<string, number>[];
    labels: string[];
    yKeys: string[];
  };
  isLoading: boolean;
  onActivePointChange?: (index: number | null) => void;
}

export function HoldingsChart({ instrumentData, isLoading, onActivePointChange }: HoldingsChartProps) {
  const colors = useColors();
  const CHART_UI = colors.chartUI;

  const handleChartHover = useCallback(
    (_event: ChartEvent, elements: ActiveElement[]) => {
      if (elements.length > 0) {
        onActivePointChange?.(elements[0].index);
      }
    },
    [onActivePointChange],
  );

  const crosshairPlugin: Plugin<'line'> = useMemo(
    () => ({
      id: 'holdingsCrosshair',
      beforeDraw(chart) {
        const activeElements = chart.getActiveElements();
        if (activeElements.length === 0) return;

        const x = activeElements[0].element.x;
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
    [CHART_UI],
  );

  if (isLoading) {
    return (
      <div className="h-72 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-brand-light border-t-transparent"></div>
      </div>
    );
  }

  if (!instrumentData || instrumentData.data.length === 0) {
    return (
      <div className="h-72 flex items-center justify-center">
        <div className="text-center">
          <p className="text-text-muted text-sm mb-2">No holdings data available</p>
          <p className="text-text-subtle text-xs">Historical data may not be available for the selected time period</p>
        </div>
      </div>
    );
  }

  const { data: holdingsData, labels, yKeys } = instrumentData;

  const datasets = yKeys.map((symbol, index) => ({
    label: symbol,
    data: holdingsData.map((dataPoint) => dataPoint[symbol] || 0),
    borderColor: colors.chart[index % colors.chart.length],
    backgroundColor: colors.chart[index % colors.chart.length] + '20',
    borderWidth: 2,
    fill: false,
    tension: 0.1,
    pointRadius: 0,
    pointHoverRadius: 5,
    pointBackgroundColor: colors.chart[index % colors.chart.length],
    pointBorderColor: colors.chart[index % colors.chart.length],
  }));

  const data = {
    labels: labels,
    datasets,
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    onHover: handleChartHover,
    plugins: {
      legend: {
        display: true,
        position: 'bottom' as const,
        labels: {
          color: CHART_UI.tickColor,
          font: { size: 11 },
          padding: 15,
          usePointStyle: true,
          pointStyle: 'circle' as const,
        },
      },
      tooltip: { enabled: false },
    },
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { color: CHART_UI.tickColor, font: { size: 11 }, maxTicksLimit: 6, autoSkip: true },
      },
      y: {
        grid: { color: CHART_UI.gridColor },
        ticks: {
          color: CHART_UI.tickColor,
          font: { size: 11 },
          callback: (value: string | number) => {
            const numValue = typeof value === 'string' ? parseFloat(value) : value;
            if (numValue >= 1000000) return `$${(numValue / 1000000).toFixed(1)}M`;
            if (numValue >= 1000) return `$${(numValue / 1000).toFixed(0)}k`;
            return `$${numValue.toFixed(0)}`;
          },
        },
      },
    },
  };

  return (
    <div className="space-y-4">
      <div className="h-72">
        <Line data={data} options={options} plugins={[crosshairPlugin]} />
      </div>
    </div>
  );
}
