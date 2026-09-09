import { getChainName } from '../constants/business/wallets';
import type { DerivedAddress, HardwareWalletImport, Wallet } from '../types';

export function importAddressKey(address: DerivedAddress): string {
  const chain = getChainName(address.networkType);
  return `${chain}:${chain === 'bitcoin' ? address.address : address.address.toLowerCase()}`;
}

export function importOnEvmNetwork<T extends HardwareWalletImport>(data: T, network: 'ETH' | 'BASE'): T {
  return {
    ...data,
    addresses: data.addresses.map((address) =>
      address.networkType === 'BTC' ? address : { ...address, networkType: network },
    ),
  };
}

export function importedParentKey(address: DerivedAddress, data: HardwareWalletImport) {
  const index = data.addresses.findIndex(
    (candidate) =>
      importAddressKey(candidate) === importAddressKey(address) && candidate.derivationPath === address.derivationPath,
  );
  if (index < 0) return undefined;
  const path = address.derivationPath.slice(0, address.derivationPath.lastIndexOf('/'));
  const matches = data.parentKeys.filter((key) => key.parentDerivationPath === path);
  return matches.length === 1 ? matches[0] : undefined;
}

export function canDeriveNextWalletAddress(wallet: Wallet, wallets: Wallet[]): boolean {
  if (!wallet.masterFingerprint || !wallet.parentPublicKey || !wallet.parentChainCode || !wallet.parentDerivationPath)
    return false;
  return !wallets.some(
    (candidate) =>
      candidate.userAccount === wallet.userAccount &&
      getChainName(candidate.chain) === getChainName(wallet.chain) &&
      candidate.masterFingerprint === wallet.masterFingerprint &&
      candidate.parentDerivationPath === wallet.parentDerivationPath &&
      candidate.addressIndex === (wallet.addressIndex ?? 0) + 1,
  );
}
