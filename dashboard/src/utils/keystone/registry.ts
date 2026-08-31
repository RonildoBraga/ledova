import {
  CryptoKeypath,
  DataItem,
  PathComponent,
  RegistryItem,
  RegistryType,
  extend,
  patchTags,
  type DataItemMap,
} from '@keystonehq/bc-ur-registry';
import { parse as parseUuid } from 'uuid';

const registryTypes = {
  ETH_SIGN_REQUEST: new RegistryType('eth-sign-request', 401),
  ETH_SIGNATURE: new RegistryType('eth-signature', 402),
  BTC_SIGN_REQUEST: new RegistryType('btc-sign-request', 8101),
  BTC_SIGNATURE: new RegistryType('btc-signature', 8102),
};

const { decodeToDataItem, RegistryTypes } = extend;

patchTags(Object.values(registryTypes).map((registryType) => registryType.getTag()));

export enum EthDataType {
  transaction = 1,
  typedData = 2,
  personalMessage = 3,
  typedTransaction = 4,
}

export enum BtcDataType {
  message = 1,
}

class KeystoneRegistryItem extends RegistryItem {
  constructor(
    private readonly registryType: RegistryType,
    private readonly dataItem: DataItem,
  ) {
    super();
  }

  getRegistryType = () => this.registryType;

  toDataItem = () => this.dataItem;
}

function createKeypath(path: string, sourceFingerprint: string): CryptoKeypath {
  const components = path
    .replace(/^[mM]\//, '')
    .split('/')
    .map(
      (component) =>
        new PathComponent({
          index: Number.parseInt(component.replace("'", ''), 10),
          hardened: component.endsWith("'"),
        }),
    );

  return new CryptoKeypath(components, Buffer.from(sourceFingerprint, 'hex'));
}

function taggedUuid(uuid: string): DataItem {
  return new DataItem(Buffer.from(parseUuid(uuid)), RegistryTypes.UUID.getTag());
}

function taggedKeypath(path: string, sourceFingerprint: string): DataItem {
  const keypath = createKeypath(path, sourceFingerprint);
  const dataItem = keypath.toDataItem();
  dataItem.setTag(keypath.getRegistryType().getTag());
  return dataItem;
}

export function createEthSignRequest(
  signData: Buffer,
  dataType: EthDataType,
  derivationPath: string,
  sourceFingerprint: string,
  requestId?: string,
  chainId?: number,
  address?: string,
  origin?: string,
): RegistryItem {
  const map: DataItemMap = {
    2: signData,
    3: dataType,
    5: taggedKeypath(derivationPath, sourceFingerprint),
  };

  if (requestId) map[1] = taggedUuid(requestId);
  if (chainId) map[4] = Number(chainId);
  if (address) map[6] = Buffer.from(address.replace(/^0x/, ''), 'hex');
  if (origin) map[7] = origin;

  return new KeystoneRegistryItem(registryTypes.ETH_SIGN_REQUEST, new DataItem(map));
}

export function createBtcSignRequest(
  requestId: string,
  sourceFingerprints: string[],
  signData: Buffer,
  dataType: BtcDataType,
  derivationPaths: string[],
  addresses?: string[],
  origin?: string,
): RegistryItem {
  const map: DataItemMap = {
    1: taggedUuid(requestId),
    2: signData,
    3: dataType || BtcDataType.message,
    4: derivationPaths.map((path, index) => taggedKeypath(path, sourceFingerprints[index])),
  };

  if (addresses) map[5] = addresses;
  if (origin) map[6] = origin;

  return new KeystoneRegistryItem(registryTypes.BTC_SIGN_REQUEST, new DataItem(map));
}

function decodeSignature(cborPayload: Buffer): Buffer {
  const data = decodeToDataItem(cborPayload).getData() as DataItemMap;
  return data[2] as Buffer;
}

export function decodeEthSignature(cborPayload: Buffer): Buffer {
  return decodeSignature(cborPayload);
}

export function decodeBtcSignature(cborPayload: Buffer): Buffer {
  return decodeSignature(cborPayload);
}
