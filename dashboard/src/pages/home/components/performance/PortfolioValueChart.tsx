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
  Filler,
  type Plugin,
  type ChartEvent,
  type ActiveElement,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { useColors } from '@hooks/useColors';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

interface ChartData {
  labels: string[];
  values: number[];
}

interface PortfolioValueChartProps {
  chartData: ChartData | null;
  isLoading: boolean;
  error: unknown;
  onActivePointChange?: (index: number | null) => void;
}

export function PortfolioValueChart({ chartData, isLoading, error, onActivePointChange }: PortfolioValueChartProps) {
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
      id: 'performanceCrosshair',
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

  const data = useMemo(() => {
    if (!chartData) return null;
    return {
      labels: chartData.labels,
      datasets: [
        {
          label: 'Portfolio Value',
          data: chartData.values,
          borderColor: CHART_UI.lineColor,
          backgroundColor: CHART_UI.lineBackground,
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 6,
          pointHoverBackgroundColor: CHART_UI.lineColor,
          pointHoverBorderColor: CHART_UI.lineColor,
          pointBackgroundColor: CHART_UI.lineColor,
        },
      ],
    };
  }, [chartData, CHART_UI]);

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      onHover: handleChartHover,
      plugins: {
        legend: { display: false },
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
    }),
    [handleChartHover, CHART_UI],
  );

  if (isLoading) {
    return (
      <div className="h-72 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-brand-light border-t-transparent"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-72 flex items-center justify-center">
        <p className="text-error-light text-sm">Error loading chart data</p>
      </div>
    );
  }

  if (!chartData || !data) {
    return (
      <div className="h-72 flex items-center justify-center">
        <p className="text-text-muted text-sm">No data available</p>
      </div>
    );
  }

  return (
    <div className="h-72">
      <Line data={data} options={options} plugins={[crosshairPlugin]} />
    </div>
  );
}
