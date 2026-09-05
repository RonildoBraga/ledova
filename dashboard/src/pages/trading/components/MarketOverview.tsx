import { Link } from 'react-router-dom';
import { SpinnerGapIcon } from '@phosphor-icons/react';
import type { ShareToken } from '@ledova/shared';
import { formatCurrency, DESIGN_TOKENS, DIRECTORY_COPY } from '@ledova/shared';
import { Panel } from '@components/Panel';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;
const ICON_LG = DESIGN_TOKENS.icon.sizes.lg;

interface MarketOverviewProps {
  tokens: ShareToken[];
  selectedTokenUuid: string | null;
  onSelectToken: (uuid: string) => void;
  isLoading: boolean;
  isEligible: boolean;
}

export function MarketOverview({
  tokens,
  selectedTokenUuid,
  onSelectToken,
  isLoading,
  isEligible,
}: MarketOverviewProps) {
  if (isLoading) {
    return (
      <Panel title="Market" icon={<SpinnerGapIcon size={ICON_SM} className="animate-spin" />}>
        <div className="flex items-center justify-center py-12">
          <SpinnerGapIcon size={ICON_LG} className="text-brand-mid animate-spin" />
        </div>
      </Panel>
    );
  }

  if (tokens.length === 0) {
    return (
      <Panel title="Market">
        <div className="py-8 px-4 text-center space-y-3">
          <p className="text-sm font-medium text-text-primary">
            {isEligible ? DIRECTORY_COPY.MARKET_EMPTY_TITLE : DIRECTORY_COPY.INELIGIBLE_TITLE}
          </p>
          <p className="text-sm text-text-muted max-w-xl mx-auto">
            {isEligible ? DIRECTORY_COPY.MARKET_EMPTY_BODY : DIRECTORY_COPY.MARKET_INELIGIBLE_BODY}
          </p>
          {!isEligible && (
            <Link to="/investor-eligibility" className="inline-block text-sm font-medium text-brand-light">
              Verify my investor status
            </Link>
          )}
        </div>
      </Panel>
    );
  }

  return (
    <div className="bg-surface-raised rounded-xl border border-border-subtle overflow-hidden">
      <div className="px-4 py-4 border-b border-border-subtle">
        <h2 className="text-base font-semibold text-text-primary">Market</h2>
        <p className="text-xs text-text-muted mt-0.5">Select a token to view orders and trade</p>
      </div>

      <div className="grid grid-cols-12 gap-2 px-4 py-2.5 text-xs font-medium text-text-muted border-b border-border-subtle/50">
        <div className="col-span-2">Token</div>
        <div className="col-span-4">Company</div>
        <div className="col-span-3 text-right">Last Price</div>
        <div className="col-span-3 text-right">Supply</div>
      </div>

      {tokens.map((token) => {
        const isSelected = token.uuid === selectedTokenUuid;
        const lastPrice = token.lastPrice ? parseFloat(token.lastPrice) : null;
        const bestBid = token.bestBid ? parseFloat(token.bestBid) : null;
        const displayPrice = lastPrice ?? bestBid;

        return (
          <button
            key={token.uuid}
            onClick={() => onSelectToken(token.uuid)}
            className={`w-full grid grid-cols-12 gap-2 items-center px-4 py-3 text-sm transition-colors border-b border-border-subtle/30 last:border-b-0 ${
              isSelected
                ? 'bg-brand-mid/10 border-l-2 border-l-brand-mid'
                : 'hover:bg-surface-tertiary/50 border-l-2 border-l-transparent'
            }`}
          >
            <div className="col-span-2 flex items-center gap-2">
              <span className={`font-bold ${isSelected ? 'text-brand-light' : 'text-text-primary'}`}>
                {token.symbol}
              </span>
            </div>
            <div className="col-span-4 text-left">
              <span className="text-text-muted truncate">{token.companyName || token.name}</span>
            </div>
            <div className="col-span-3 text-right font-mono">
              {displayPrice !== null ? (
                <span className="text-text-primary">{formatCurrency(displayPrice)}</span>
              ) : (
                <span className="text-text-subtle">--</span>
              )}
            </div>
            <div className="col-span-3 text-right">
              <span className="text-text-muted">{token.totalSupply ? token.totalSupply.toLocaleString() : '0'}</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
