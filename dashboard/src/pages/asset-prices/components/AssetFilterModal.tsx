import { FunnelIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';
import { Modal } from '@components/Modal';

const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

type SortOption = 'alphabetical' | 'assetType';

interface AssetFilterModalProps {
  isOpen: boolean;
  searchQuery: string;
  selectedSort: SortOption;
  selectedAssetType: string;
  assetTypes: string[];
  onClose: () => void;
  onSearchChange: (value: string) => void;
  onSortChange: (value: SortOption) => void;
  onAssetTypeChange: (value: string) => void;
  onApply: () => void;
  onClear: () => void;
}

const sortOptions = [
  { value: 'assetType' as SortOption, label: 'Type' },
  { value: 'alphabetical' as SortOption, label: 'A-Z' },
];

export function AssetFilterModal({
  isOpen,
  searchQuery,
  selectedSort,
  selectedAssetType,
  assetTypes,
  onClose,
  onSearchChange,
  onSortChange,
  onAssetTypeChange,
  onApply,
  onClear,
}: AssetFilterModalProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      showFooter
      cancelLabel="Clear"
      confirmLabel="Apply"
      onConfirm={onApply}
      onCancel={onClear}
      size="sm"
    >
      {/* Header */}
      <div className="flex flex-col items-center pb-3">
        <FunnelIcon size={ICON_LG} className="text-brand-mid mb-1" />
        <h3 className="text-lg font-semibold text-text-primary">Filter Assets</h3>
      </div>

      <div className="space-y-4">
        {/* Search */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-text-subtle uppercase tracking-wide">Search</p>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search by name or symbol..."
            className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand-mid"
          />
        </div>

        {/* Sort */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-text-subtle uppercase tracking-wide">Sort By</p>
          <div className="grid grid-cols-2 gap-2">
            {sortOptions.map((option) => {
              const isSelected = selectedSort === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => onSortChange(option.value)}
                  className={`px-3 py-2 text-xs font-medium rounded-lg border-2 transition-colors ${
                    isSelected
                      ? 'border-brand-mid bg-surface-disabled text-brand-light'
                      : 'border-transparent bg-surface-tertiary text-text-secondary hover:bg-surface-disabled'
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Asset Type */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-text-subtle uppercase tracking-wide">Asset Type</p>
          <select
            value={selectedAssetType}
            onChange={(e) => onAssetTypeChange(e.target.value)}
            className="w-full bg-surface-tertiary border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-mid"
          >
            <option value="">All types</option>
            {assetTypes.map((type) => (
              <option key={type} value={type}>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </option>
            ))}
          </select>
        </div>
      </div>
    </Modal>
  );
}
