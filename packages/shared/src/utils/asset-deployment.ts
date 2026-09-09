import type { AssetChainDeployment, Wallet, WalletHolding } from '../types';

export function getHoldingTokenDeployment(
  holding: WalletHolding,
  wallet: Pick<Wallet, 'uuid' | 'chain'>,
): AssetChainDeployment | null {
  if (
    holding.walletUuid !== wallet.uuid ||
    holding.chain !== wallet.chain ||
    !holding.asset?.isActive ||
    holding.asset.assetType === 'native_crypto'
  )
    return null;

  const deployments = holding.asset.chainDeployments?.filter((row) => row.chain === wallet.chain && row.isActive) ?? [];
  if (deployments.length !== 1) return null;
  const deployment = deployments[0];
  if (
    !deployment ||
    !deployment.contractAddress ||
    !Number.isInteger(deployment.decimals) ||
    deployment.decimals < 0 ||
    deployment.decimals > 255
  )
    return null;
  return deployment;
}
