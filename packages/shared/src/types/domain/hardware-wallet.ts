export type HardwareWalletNetworkType = 'ETH' | 'BTC';

export interface DerivedAddress {
  address: string;

  addressIndex: number;

  derivationPath: string;

  networkType: HardwareWalletNetworkType;
}

export interface ParentKeyData {
  parentPublicKey: string;

  parentChainCode: string;

  parentDerivationPath: string;
}

export interface HardwareWalletImport {
  addresses: DerivedAddress[];

  masterFingerprint: string;

  parentKeys: ParentKeyData[];
}
