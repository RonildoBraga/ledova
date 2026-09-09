import {
  canDeriveNextWalletAddress,
  importAddressKey,
  importedParentKey,
  importOnEvmNetwork,
} from '../../src/utils/wallet-import';
import type { DerivedAddress, HardwareWalletImport, ParentKeyData, Wallet } from '../../src/types';

const address: DerivedAddress = {
  address: '0xaB',
  networkType: 'ETH',
  addressIndex: 0,
  derivationPath: "m/44'/60'/0'/0/0",
};
const bitcoin: DerivedAddress = { ...address, address: 'mAbC', networkType: 'BTC', derivationPath: "m/84'/1'/0'/0/0" };
const keys: [ParentKeyData, ParentKeyData] = [
  { parentPublicKey: 'evm-public', parentChainCode: 'evm-chain', parentDerivationPath: "m/44'/60'/0'/0" },
  { parentPublicKey: 'btc-public', parentChainCode: 'btc-chain', parentDerivationPath: "m/84'/1'/0'/0" },
];
const data: HardwareWalletImport = {
  addresses: [address, bitcoin],
  parentKeys: keys,
  masterFingerprint: 'fingerprint',
};

it('changes only the chosen EVM network and preserves key material', () => {
  const selected = importOnEvmNetwork(data, 'BASE');
  expect(selected.addresses.map((row) => row.networkType)).toEqual(['BASE', 'BTC']);
  expect(data.addresses).toEqual([address, bitcoin]);
  expect(selected.masterFingerprint).toBe(data.masterFingerprint);
  expect(selected.parentKeys).toBe(keys);
});

it('selects the parent by exact path when an import omits or reorders addresses', () => {
  expect(importedParentKey(bitcoin, data)).toBe(keys[1]);
  expect(importedParentKey(bitcoin, { ...data, parentKeys: [keys[1], keys[0]] })).toBe(keys[1]);
  expect(importedParentKey(bitcoin, { ...data, parentKeys: [keys[1], keys[1]] })).toBeUndefined();
  expect(importedParentKey({ ...bitcoin, derivationPath: "m/84'/1'/0'/00/0" }, data)).toBeUndefined();
});

it('folds EVM address case and preserves Bitcoin case', () => {
  expect(importAddressKey(address)).toBe(importAddressKey({ ...address, address: address.address.toLowerCase() }));
  expect(importAddressKey(bitcoin)).not.toBe(importAddressKey({ ...bitcoin, address: bitcoin.address.toLowerCase() }));
});

it('derives the next address separately for each account and network', () => {
  const wallet = {
    userAccount: 'account',
    chain: 'base',
    masterFingerprint: 'fingerprint',
    ...keys[0],
    addressIndex: 0,
  } as Wallet;
  const next = { ...wallet, addressIndex: 1 };
  expect(
    canDeriveNextWalletAddress(wallet, [
      { ...next, chain: 'ethereum' },
      { ...next, userAccount: 'other' },
    ]),
  ).toBe(true);
  expect(canDeriveNextWalletAddress(wallet, [next])).toBe(false);
  expect(canDeriveNextWalletAddress({ ...wallet, parentPublicKey: undefined }, [])).toBe(false);
});
