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
    valueSource: overrides.currentPrice == null ? 'unpriced' : 'market',
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
    walletUuid: 'wallet-uuid',
    walletAddress: `0x${'a'.repeat(40)}`,
    chain: 'base',
    asset: asset({}),
    assetSymbol: 'ORD',
    assetName: 'Acme Ordinary',
    quantity: '250.000000000000000000',
    marketValue: null,
    valueSource: overrides.marketValue == null ? 'unpriced' : 'market',
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

  it('weights the doughnut by quantity when nothing on the page has a price', () => {
    const allocation = calculateAssetAllocation(shares, calculateHoldingsSummary(shares, 1).totalValue);

    expect(allocation.map((item) => [item.symbol, item.percentage])).toEqual([['ORD', 100]]);
  });

  it('splits an unpriced doughnut between two share classes by how many are held', () => {
    const other = holding({
      uuid: 'pref-holding',
      asset: asset({ uuid: 'pref-uuid', symbol: 'PREF' }),
      assetSymbol: 'PREF',
      assetName: 'Acme Preference',
      quantity: '750.000000000000000000',
    });

    const allocation = calculateAssetAllocation([...shares, other], 0);

    expect(allocation.map((item) => [item.symbol, item.percentage])).toEqual([
      ['PREF', 75],
      ['ORD', 25],
    ]);
  });

  it('stays empty when there is genuinely nothing held', () => {
    expect(calculateAssetAllocation([], 0)).toEqual([]);
  });

  it('stays empty when a holding is of nothing at all', () => {
    expect(calculateAssetAllocation([holding({ quantity: '0' })], 0)).toEqual([]);
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

describe('a slice says what its share is a share of', () => {
  const shares = holding({ assetSymbol: 'ORD', asset: asset({ uuid: 'ord' }) });
  const stablecoin = holding({
    assetSymbol: 'USDC',
    assetName: 'USD Coin',
    quantity: '12',
    marketValue: '12.00',
    asset: asset({ uuid: 'usdc', symbol: 'USDC', name: 'USD Coin', currentPrice: '1.00' }),
  });

  it('says quantity when nothing on the page carried a price, because that is what it weighed by', () => {
    expect(calculateAssetAllocation([shares], 0).map((item) => item.basis)).toEqual(['quantity']);
  });

  it('says unpriced for the holding a value-weighted page could not count', () => {
    expect(calculateAssetAllocation([shares, stablecoin], 12).map((item) => [item.symbol, item.basis])).toEqual([
      ['USDC', 'value'],
      ['ORD', 'unpriced'],
    ]);
  });

  it('says value for a priced holding the wallet has since emptied, rather than calling it unpriced', () => {
    const emptied = holding({
      assetSymbol: 'USDC',
      quantity: '0',
      marketValue: '0.00',
      asset: asset({ uuid: 'usdc', symbol: 'USDC', currentPrice: '1.00' }),
    });

    expect(calculateAssetAllocation([emptied, stablecoin], 12).map((item) => item.basis)).toEqual(['value']);
  });

  it('reads whether a price came back rather than whether it was positive', () => {
    const worthless = holding({ quantity: '5', marketValue: '0.00', asset: asset({ currentPrice: '0.00' }) });

    expect(calculateAssetAllocation([worthless, stablecoin], 12).map((item) => [item.symbol, item.basis])).toEqual([
      ['USDC', 'value'],
      ['ORD', 'value'],
    ]);
  });
});

describe('valuation provenance beside the percentage basis', () => {
  it('values market, NAV and par together while leaving the unknown holding out', () => {
    const holdings = [
      holding({ asset: asset({ uuid: 'eth' }), assetSymbol: 'ETH', marketValue: '20', valueSource: 'market' }),
      holding({ asset: asset({ uuid: 'nav' }), assetSymbol: 'AUSG', marketValue: '5', valueSource: 'nav' }),
      holding({ asset: asset({ uuid: 'par' }), assetSymbol: 'AUDY', marketValue: '5', valueSource: 'par' }),
      holding(),
    ];
    const summary = calculateHoldingsSummary(holdings, 1);
    const allocation = calculateAssetAllocation(holdings, summary.totalValue);
    expect(summary.totalValue).toBe(30);
    expect(allocation.map(({ symbol, totalValue, source, basis }) => ({ symbol, totalValue, source, basis }))).toEqual([
      { symbol: 'ETH', totalValue: 20, source: 'market', basis: 'value' },
      { symbol: 'AUSG', totalValue: 5, source: 'nav', basis: 'value' },
      { symbol: 'AUDY', totalValue: 5, source: 'par', basis: 'value' },
      { symbol: 'ORD', totalValue: 0, source: 'unpriced', basis: 'unpriced' },
    ]);
    expect(allocation[1]?.percentage).toBeCloseTo(100 / 6);
  });

  it('retains unpriced provenance when the whole chart weighs by quantity', () => {
    const allocation = calculateAssetAllocation([holding()], 0);
    expect(allocation[0]).toMatchObject({ source: 'unpriced', basis: 'quantity', percentage: 100 });
  });

  it.each([null, '', 'NaN', 'Infinity', '-1'])('does not use a NAV marker to invent a value for %s', (marketValue) => {
    const holdings = [holding({ marketValue, valueSource: 'nav' })];
    expect(calculateHoldingsSummary(holdings, 1).totalValue).toBe(0);
    expect(calculateAssetAllocation(holdings, 0)[0]?.source).toBe('unpriced');
  });

  it('does not mistake an untagged cached amount for a market quote', () => {
    const holdings = [holding({ marketValue: '99', valueSource: 'unpriced' })];
    expect(calculateHoldingsSummary(holdings, 1).totalValue).toBe(0);
    expect(calculateAssetAllocation(holdings, 0)[0]).toMatchObject({
      source: 'unpriced',
      totalValue: 0,
      basis: 'quantity',
    });
  });
});
