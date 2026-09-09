import { getHoldingTokenDeployment } from '../../src/utils/asset-deployment';
import type { AssetChainDeployment, WalletHolding } from '../../src/types';

const wallet = { uuid: 'base-wallet', chain: 'base' };
const ethereum: AssetChainDeployment = {
  uuid: 'eth-deployment',
  chain: 'ethereum',
  contractAddress: `0x${'1'.repeat(40)}`,
  decimals: 18,
  isActive: true,
};
const base: AssetChainDeployment = {
  uuid: 'base-deployment',
  chain: 'base',
  contractAddress: `0x${'2'.repeat(40)}`,
  decimals: 0,
  isActive: true,
};
function holding(): WalletHolding {
  return {
    uuid: 'holding',
    walletUuid: wallet.uuid,
    walletAddress: `0x${'a'.repeat(40)}`,
    chain: 'base',
    assetSymbol: 'MULTI',
    assetName: 'Multi-network token',
    quantity: '3',
    marketValue: null,
    valueSource: 'unpriced',
    createdAt: '',
    updatedAt: '',
    lastSyncedAt: '',
    asset: {
      uuid: 'asset',
      symbol: 'MULTI',
      name: 'Multi-network token',
      assetType: 'erc20_token',
      chain: 'ethereum',
      contractAddress: ethereum.contractAddress,
      decimals: 18,
      chainDeployments: [ethereum, base],
      currentPrice: null,
      priceCurrency: 'USD',
      valueSource: 'unpriced',
      isActive: true,
      createdAt: '',
      updatedAt: '',
    },
  };
}

describe('the selected wallet determines its transferable deployment', () => {
  it('uses Base contract and zero decimals even when the asset summary names Ethereum', () => {
    expect(getHoldingTokenDeployment(holding(), wallet)).toEqual(base);
  });
  it('does not use holdings from another wallet or network', () => {
    expect(getHoldingTokenDeployment({ ...holding(), walletUuid: 'other' }, wallet)).toBeNull();
    expect(getHoldingTokenDeployment({ ...holding(), chain: 'ethereum' }, wallet)).toBeNull();
  });
  it('does not fall back to the summary contract when the deployment is absent', () => {
    const row = holding();
    row.asset.chainDeployments = [ethereum];
    expect(getHoldingTokenDeployment(row, wallet)).toBeNull();
    delete row.asset.chainDeployments;
    expect(getHoldingTokenDeployment(row, wallet)).toBeNull();
  });
  it('refuses disabled, contract-less, ambiguous and invalid-decimal deployments', () => {
    for (const deployments of [
      [{ ...base, isActive: false }],
      [{ ...base, contractAddress: null }],
      [base, { ...base, uuid: 'duplicate' }],
      [{ ...base, decimals: -1 }],
      [{ ...base, decimals: 1.5 }],
      [{ ...base, decimals: 256 }],
    ]) {
      const row = holding();
      row.asset.chainDeployments = deployments;
      expect(getHoldingTokenDeployment(row, wallet)).toBeNull();
    }
  });
  it('refuses inactive assets and native coins carrying a mistaken contract address', () => {
    const row = holding();
    row.asset.isActive = false;
    expect(getHoldingTokenDeployment(row, wallet)).toBeNull();
    row.asset.isActive = true;
    row.asset.assetType = 'native_crypto';
    expect(getHoldingTokenDeployment(row, wallet)).toBeNull();
  });
});
