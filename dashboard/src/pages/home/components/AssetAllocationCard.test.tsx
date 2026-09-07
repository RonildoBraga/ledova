// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, fireEvent, render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { calculateAssetAllocation } from '@ledova/shared';
import type { HoldingWithWallet, HoldingsSummary } from '@ledova/shared';

const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

const drawn: { data: { datasets: { data: number[] }[]; labels: string[] }; options: TooltipOptions }[] = [];

interface TooltipOptions {
  plugins: { tooltip: { callbacks: { label: (context: { dataIndex: number }) => string } } };
}

vi.mock('react-chartjs-2', () => ({
  Doughnut: (props: { data: (typeof drawn)[number]['data']; options: TooltipOptions }) => {
    drawn.push({ data: props.data, options: props.options });
    return null;
  },
}));

const { AssetAllocationCard } = await import('./AssetAllocationCard');

function holding(symbol: string, quantity: string, marketValue: string | null, chain = 'base'): HoldingWithWallet {
  return {
    uuid: `holding-${symbol}-${chain}`,
    assetSymbol: symbol,
    assetName: `${symbol} Asset`,
    quantity,
    marketValue,
    chain,
    asset: { uuid: `asset-${symbol}`, symbol, name: `${symbol} Asset` },
    walletInfo: { uuid: `wallet-${chain}`, name: 'Wallet', address: '0x0', chain },
  } as unknown as HoldingWithWallet;
}

function draw(holdings: HoldingWithWallet[], totalValue: number) {
  drawn.length = 0;
  const summary = {
    totalValue,
    holdingsCount: holdings.length,
    walletsCount: 1,
    byAssetType: [],
  } satisfies HoldingsSummary;
  const view = render(
    <QueryClientProvider client={client}>
      <AssetAllocationCard
        assetAllocation={calculateAssetAllocation(holdings, totalValue)}
        totalValue={totalValue}
        summary={summary}
        isLoading={false}
        hasError={false}
        onAssetClick={() => {}}
      />
    </QueryClientProvider>,
  );
  return { ...drawn[drawn.length - 1], view };
}

const UNPRICED = [holding('AAA', '30', null), holding('BBB', '10', null)];
const MIXED = [holding('SHARES', '10000', null), holding('USDC', '12', '12')];

beforeEach(() => {
  drawn.length = 0;
});

afterEach(() => {
  cleanup();
  client.clear();
});

describe('what the dashboard ring is handed, not what the function returns', () => {
  it('draws arcs from the shares the function chose, so the unpriced fallback reaches the ring', () => {
    const { data } = draw(UNPRICED, 0);

    expect(data.labels).toEqual(['AAA', 'BBB']);
    expect(data.datasets[0].data).toEqual([75, 25]);
  });

  it('agrees with the list beneath it, which reads the same shares', () => {
    const { data, view } = draw(UNPRICED, 0);

    expect(data.datasets[0].data).toEqual([75, 25]);
    expect(view.getByText('75.0%')).toBeTruthy();
    expect(view.getByText('25.0%')).toBeTruthy();
  });

  it('names the basis in the tooltip rather than dividing by a total of zero', () => {
    const { options } = draw(UNPRICED, 0);

    expect(options.plugins.tooltip.callbacks.label({ dataIndex: 0 })).toBe('AAA: unpriced (75.0% by quantity)');
  });

  it('draws the priced share of a mixed portfolio and leaves the 0% slice out of the ring', () => {
    const { data } = draw(MIXED, 12);

    expect(data.labels).toEqual(['USDC']);
    expect(data.datasets[0].data).toEqual([100]);
  });

  it('says the total excludes what it could not price', () => {
    const { view } = draw(MIXED, 12);

    expect(view.getByText('excludes 1 unpriced holding')).toBeTruthy();
    expect(view.getByText('unpriced')).toBeTruthy();
  });

  it('prints no percentage beside unpriced, so the label has no number arguing with it', () => {
    const { view } = draw(MIXED, 12);

    expect(view.container.textContent).toContain('SHARES Asset10,000unpriced—');
    expect(view.container.textContent).not.toContain('unpriced0.0%');
  });

  it('keeps the percentage when the whole page is weighed by quantity, since then it means something', () => {
    const { view } = draw(UNPRICED, 0);

    expect(view.container.textContent).toContain('AAA Asset30unpriced75.0%');
    expect(view.container.textContent).toContain('BBB Asset10unpriced25.0%');
  });
});

describe('one coin held on two chains, which the ring draws as one', () => {
  const ACROSS = [holding('USDC', '300', '300', 'ethereum'), holding('USDC', '100', '100', 'base')];

  it('draws one arc and one line, whatever it is spread over', () => {
    const { data, view } = draw(ACROSS, 400);

    expect(data.labels).toEqual(['USDC']);
    expect(data.datasets[0].data).toEqual([100]);
    expect(view.queryAllByText('USDC Asset')).toHaveLength(1);
  });

  it('shows the summed quantity on the line, from the field the fold now carries', () => {
    const priced = [holding('SHR', '300', '600', 'ethereum'), holding('SHR', '100', '200', 'base')];

    const { view } = draw(priced, 800);

    expect(view.container.textContent).toContain('SHR Asset400');
  });

  it('offers the split, and does not open it until it is asked to', () => {
    const { view } = draw(ACROSS, 400);

    expect(view.container.textContent).not.toContain('ethereum');
    fireEvent.click(view.getByLabelText('Show USDC by chain'));

    expect(view.container.textContent).toContain('ethereum');
    expect(view.container.textContent).toContain('base');
  });

  it('splits the quantity and the value the line summed, largest chain first', () => {
    const { view } = draw(ACROSS, 400);
    fireEvent.click(view.getByLabelText('Show USDC by chain'));

    const chains = view.container.textContent ?? '';
    expect(chains.indexOf('ethereum')).toBeLessThan(chains.indexOf('base'));
    expect(chains).toContain('ethereum300');
    expect(chains).toContain('base100');
  });

  it('closes again, so the row is a toggle rather than a one-way door', () => {
    const { view } = draw(ACROSS, 400);
    fireEvent.click(view.getByLabelText('Show USDC by chain'));
    fireEvent.click(view.getByLabelText('Hide USDC by chain'));

    expect(view.container.textContent).not.toContain('ethereum');
  });

  it('says which chain could not be priced, while the line keeps saying it is unpriced', () => {
    const { view } = draw([holding('USDC', '300', '300', 'ethereum'), holding('USDC', '100', null, 'base')], 300);
    fireEvent.click(view.getByLabelText('Show USDC by chain'));

    expect(view.container.textContent).toContain('base100unpriced');
  });
});

describe('a coin held on one chain', () => {
  it('offers no expansion, so most rows look exactly as they did', () => {
    const { view } = draw([holding('USDC', '100', '100', 'base')], 100);

    expect(view.queryByLabelText('Show USDC by chain')).toBeNull();
    expect(view.container.textContent).not.toContain('base');
  });
});
