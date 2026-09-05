import { calculateAssetAllocation, calculateHoldingsSummary } from '../../src/utils/holdings';
import { getHoldingAssetTypeLabel, HOLDING_ASSET_TYPE } from '../../src/constants';
import type { Asset, HoldingWithWallet } from '../../src/types';

function asset(overrides: Partial<Asset>): Asset {
  return {
    uuid: 'asset-uuid',
    symbol: 'ORD',
    name: 'Acme Ordinary',
    assetType: HOLDING_ASSET_TYPE.TOKENIZED_SECURITY,
    chain: 'base',
    contractAddress: `0x${'5e'.repeat(20)}`,
    decimals: 0,
    currentPrice: null,
    priceCurrency: 'USD',
    isActive: true,
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    ...overrides,
  };
}

function holding(overrides: Partial<HoldingWithWallet> = {}): HoldingWithWallet {
  return {
    uuid: 'holding-uuid',
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    wallet: 'wallet-uuid',
    walletAddress: `0x${'a'.repeat(40)}`,
    asset: asset({}),
    assetSymbol: 'ORD',
    assetName: 'Acme Ordinary',
    quantity: '250.000000000000000000',
    marketValue: null as unknown as string,
    lastSyncedAt: '2026-09-01T00:00:00Z',
    walletInfo: { uuid: 'wallet-uuid', name: undefined, address: `0x${'a'.repeat(40)}`, chain: 'base' },
    ...overrides,
  };
}

describe('a shares-only portfolio, priced at nothing', () => {
  const shares = [holding()];

  it('summarises the share holding under Tokenized Securities at zero value', () => {
    const summary = calculateHoldingsSummary(shares, 1);

    expect(summary.totalValue).toBe(0);
    expect(summary.holdingsCount).toBe(1);
    expect(summary.byAssetType).toEqual([
      {
        assetType: HOLDING_ASSET_TYPE.TOKENIZED_SECURITY,
        label: getHoldingAssetTypeLabel(HOLDING_ASSET_TYPE.TOKENIZED_SECURITY),
        totalValue: 0,
        holdingsCount: 1,
      },
    ]);
    expect(summary.byAssetType[0]?.label).toBe('Tokenized Securities');
  });

  it('leaves the allocation doughnut empty because the total is zero', () => {
    expect(calculateAssetAllocation(shares, calculateHoldingsSummary(shares, 1).totalValue)).toEqual([]);
  });

  it('still fills the doughnut once one priced holding sits beside the shares', () => {
    const priced = holding({
      uuid: 'usdc-holding',
      asset: asset({ uuid: 'usdc-uuid', symbol: 'USDC', assetType: HOLDING_ASSET_TYPE.STABLECOIN }),
      assetSymbol: 'USDC',
      assetName: 'USD Coin',
      quantity: '100.000000000000000000',
      marketValue: '100.00',
    });
    const mixed = [...shares, priced];

    const allocation = calculateAssetAllocation(mixed, calculateHoldingsSummary(mixed, 1).totalValue);

    expect(allocation.map((item) => [item.symbol, item.percentage])).toEqual([
      ['USDC', 100],
      ['ORD', 0],
    ]);
  });
});
