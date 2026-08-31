import type { TimeRange, TimeRangeConfig } from '@ledova/shared-constants';

interface TimeRangeSelectorProps {
  timeRanges: TimeRangeConfig[];
  selectedTimeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

export const TimeRangeSelector = ({ timeRanges, selectedTimeRange, onTimeRangeChange }: TimeRangeSelectorProps) => {
  return (
    <div className="bg-surface-raised rounded-lg border border-border p-1">
      <div className="flex gap-1">
        {timeRanges.map((range) => (
          <button
            key={range.value}
            type="button"
            onClick={() => onTimeRangeChange(range.value)}
            className={`flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-border-focus focus:ring-opacity-50 ${
              selectedTimeRange === range.value
                ? 'bg-brand text-white'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-tertiary'
            }`}
          >
            {range.label}
          </button>
        ))}
      </div>
    </div>
  );
};
