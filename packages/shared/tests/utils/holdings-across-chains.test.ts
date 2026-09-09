import { calculateAssetAllocation } from '../../src/utils/holdings';
import { HOLDING_ASSET_TYPE } from '../../src/constants';
import type { Asset, HoldingWithWallet } from '../../src/types';

const USDC: Asset = {
  uuid: 'usdc-uuid',
  symbol: 'USDC',
  name: 'USD Coin',
  assetType: HOLDING_ASSET_TYPE.ERC20_TOKEN,
  chain: 'base',
  contractAddress: `0x${'5e'.repeat(20)}`,
  decimals: 6,
  currentPrice: '1.00',
  priceCurrency: 'USD',
  isActive: true,
  createdAt: '2026-09-01T00:00:00Z',
  updatedAt: '2026-09-01T00:00:00Z',
};

function onChain(chain: string, quantity: string, marketValue: string | null, overrides = {}): HoldingWithWallet {
  return {
    uuid: `holding-${chain}-${quantity}`,
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    walletUuid: `wallet-${chain}`,
    walletAddress: `0x${'a'.repeat(40)}`,
    chain,
    asset: USDC,
    assetSymbol: 'USDC',
    assetName: 'USD Coin',
    quantity,
    marketValue,
    lastSyncedAt: '2026-09-01T00:00:00Z',
    walletInfo: { uuid: `wallet-${chain}`, name: undefined, address: `0x${'a'.repeat(40)}`, chain },
    ...overrides,
  } as HoldingWithWallet;
}

function onlyLine(allocation: ReturnType<typeof calculateAssetAllocation>) {
  expect(allocation).toHaveLength(1);
  const line = allocation[0];
  if (!line) throw new Error('the allocation was empty');
  return line;
}

describe('one coin held on two chains', () => {
  const held = [onChain('ethereum', '300', '300'), onChain('base', '100', '100')];

  it('is one line, because an asset is one asset wherever it is deployed', () => {
    const allocation = calculateAssetAllocation(held, 400);

    expect(allocation.map((item) => item.symbol)).toEqual(['USDC']);
    expect(onlyLine(allocation).percentage).toBe(100);
  });

  it('carries the summed quantity on the line, so nothing has to sum it again', () => {
    const allocation = calculateAssetAllocation(held, 400);

    expect(onlyLine(allocation).totalQuantity).toBe(400);
    expect(onlyLine(allocation).totalValue).toBe(400);
  });

  it('carries the split the line is a sum of, largest chain first', () => {
    const allocation = calculateAssetAllocation(held, 400);

    expect(onlyLine(allocation).perChain).toEqual([
      { chain: 'ethereum', quantity: 300, totalValue: 300, priced: true },
      { chain: 'base', quantity: 100, totalValue: 100, priced: true },
    ]);
  });

  it('adds two wallets on the same chain into one slice rather than two', () => {
    const twoOnBase = [onChain('base', '100', '100'), onChain('base', '25', '25', { uuid: 'second-base' })];

    const allocation = calculateAssetAllocation(twoOnBase, 125);

    expect(onlyLine(allocation).perChain).toEqual([{ chain: 'base', quantity: 125, totalValue: 125, priced: true }]);
  });
});

describe('a coin held on one chain only', () => {
  it('carries one slice, which is what tells a client not to offer an expansion', () => {
    const allocation = calculateAssetAllocation([onChain('base', '100', '100')], 100);

    expect(onlyLine(allocation).perChain).toHaveLength(1);
    expect(onlyLine(allocation).perChain).toEqual([{ chain: 'base', quantity: 100, totalValue: 100, priced: true }]);
  });
});

describe('a line summed across a priced chain and an unpriced one', () => {
  const mixed = [onChain('ethereum', '300', '300'), onChain('base', '100', null)];

  it('says which chain is unpriced, while the line keeps the basis it had', () => {
    const allocation = calculateAssetAllocation(mixed, 300);

    expect(onlyLine(allocation).basis).toBe('unpriced');
    expect(onlyLine(allocation).perChain).toEqual([
      { chain: 'ethereum', quantity: 300, totalValue: 300, priced: true },
      { chain: 'base', quantity: 100, totalValue: 0, priced: false },
    ]);
  });

  it('still contributes what it could price rather than dropping the line', () => {
    const allocation = calculateAssetAllocation(mixed, 300);

    expect(onlyLine(allocation).totalValue).toBe(300);
    expect(onlyLine(allocation).totalQuantity).toBe(400);
  });
});

describe('a holding whose chain the serializer did not send', () => {
  it('falls back to the wallet it came from rather than losing the row', () => {
    const noChain = onChain('base', '100', '100');
    const allocation = calculateAssetAllocation([{ ...noChain, chain: '' } as HoldingWithWallet], 100);

    expect(onlyLine(allocation).perChain).toEqual([{ chain: 'base', quantity: 100, totalValue: 100, priced: true }]);
  });
});
