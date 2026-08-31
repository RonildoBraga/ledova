export interface AssetAllocation {
  uuid: string;
  portfolio: string;
  asset: string;
  assetName: string;
  assetSymbol: string;
  assetDisplayName: string;
  assetCurrency?: string;
  percentage: string;
  currentQuantity?: number;
  currentAllocationPercentage?: string;
  currentMarketValue?: string;
}
