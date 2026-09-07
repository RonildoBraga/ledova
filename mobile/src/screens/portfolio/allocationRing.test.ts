import { calculateAssetAllocation } from '@ledova/shared';
import type { HoldingWithWallet } from '@ledova/shared';

function holding(symbol: string, quantity: string, marketValue: string): HoldingWithWallet {
  return {
    uuid: `holding-${symbol}`,
    assetSymbol: symbol,
    assetName: `${symbol} Asset`,
    quantity,
    marketValue,
    asset: { uuid: `asset-${symbol}`, symbol, name: `${symbol} Asset` },
    walletInfo: { uuid: 'wallet', name: 'Wallet', address: '0x0', chain: 'base' },
  } as unknown as HoldingWithWallet;
}

const UNPRICED = [holding('AAA', '30', '0'), holding('BBB', '10', '0')];

const drawnByTheRing = (allocation: ReturnType<typeof calculateAssetAllocation>) =>
  allocation.filter((item) => item.percentage != null && item.color && item.percentage > 0);

describe('usePortfolio hands the mobile ring the same allocation the dashboard draws', () => {
  it('gives the ring slices to draw when every holding is unpriced', () => {
    const allocation = calculateAssetAllocation(UNPRICED, 0);

    expect(allocation).not.toHaveLength(0);
    expect(drawnByTheRing(allocation)).toHaveLength(2);
  });

  it('weighs those slices by quantity, since no price can weigh them', () => {
    const allocation = calculateAssetAllocation(UNPRICED, 0);

    expect(allocation.map((item) => [item.symbol, item.percentage])).toEqual([
      ['AAA', 75],
      ['BBB', 25],
    ]);
  });

  it('leaves the ring empty when there is nothing held at all', () => {
    expect(calculateAssetAllocation([], 0)).toEqual([]);
  });

  it('leaves the ring empty when what is held is held in zero quantity', () => {
    expect(calculateAssetAllocation([holding('AAA', '0', '0')], 0)).toEqual([]);
  });

  it('still weighs by value when the holdings are priced', () => {
    const priced = [holding('AAA', '30', '10'), holding('BBB', '10', '30')];

    expect(calculateAssetAllocation(priced, 40).map((item) => [item.symbol, item.percentage])).toEqual([
      ['BBB', 75],
      ['AAA', 25],
    ]);
  });
});
