import type { PortfolioSnapshot, PortfolioSnapshotDataPoint } from '../types';

export function portfolioSnapshotPoints(snapshots: readonly PortfolioSnapshot[]): PortfolioSnapshotDataPoint[] {
  return snapshots.map((snapshot, dayIndex) => {
    const assetHoldings = snapshot.holdingsData || {};
    const assetValues: Record<string, number> = {};
    let totalMarketValue = snapshot.totalMarketValue ? parseFloat(snapshot.totalMarketValue) : 0;

    for (const [symbol, holding] of Object.entries(assetHoldings)) {
      const value = parseFloat(holding.marketValue || '0');
      assetValues[symbol] = value;
      if (!snapshot.totalMarketValue) totalMarketValue += value;
    }

    return {
      dayIndex,
      date: snapshot.snapshotDate,
      totalMarketValue,
      assetValues,
      assetHoldings,
      assetSymbols: Object.keys(assetHoldings),
    };
  });
}
