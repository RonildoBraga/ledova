import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import { Doughnut } from 'react-chartjs-2';
import { useColors } from '@hooks/useColors';
import { useCurrency } from '@hooks/useCurrency';
import type { AssetAllocationItem } from '@ledova/shared-types';

ChartJS.register(ArcElement, Tooltip, Legend);

interface AllocationPieChartProps {
  assetAllocation: AssetAllocationItem[];
  totalValue: number;
  isLoading: boolean;
}

export function AllocationPieChart({ assetAllocation, totalValue, isLoading }: AllocationPieChartProps) {
  const { formatDisplayCurrency } = useCurrency();
  const colors = useColors();
  const CHART_UI = colors.chartUI;
  const TOOLTIP = CHART_UI.tooltip;

  if (isLoading) {
    return (
      <div className="h-72 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-brand-light border-t-transparent"></div>
      </div>
    );
  }

  if (assetAllocation.length === 0) {
    return (
      <div className="h-72 flex items-center justify-center">
        <p className="text-text-muted text-sm">No allocation data available</p>
      </div>
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
        display: true,
        position: 'right' as const,
        labels: {
          color: CHART_UI.tickColor,
          font: { size: 11 },
          padding: 12,
          usePointStyle: true,
          pointStyle: 'circle',
        },
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
    cutout: '60%',
  };

  return (
    <div className="h-72 flex flex-col">
      <div className="flex-1 flex items-center justify-center">
        <div className="w-full max-w-[400px] h-full">
          <Doughnut data={data} options={options} />
        </div>
      </div>
      <div className="text-center pt-2">
        <div className="text-2xl font-bold text-text-primary">{formatDisplayCurrency(totalValue)}</div>
        <div className="text-sm text-text-muted">Total Portfolio Value</div>
      </div>
    </div>
  );
}
