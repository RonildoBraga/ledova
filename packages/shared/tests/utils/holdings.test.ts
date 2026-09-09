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
    walletUuid: 'wallet-uuid',
    walletAddress: `0x${'a'.repeat(40)}`,
    chain: 'base',
    asset: asset({}),
    assetSymbol: 'ORD',
    assetName: 'Acme Ordinary',
    quantity: '250.000000000000000000',
    marketValue: null,
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
