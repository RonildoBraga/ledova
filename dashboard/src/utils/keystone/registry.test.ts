import { describe, expect, it } from 'vitest';
import { decodeKeystoneMessageSignature } from './urDecoder';
import { encodeBitcoinMessage } from './urEncoder';
import { BtcDataType, EthDataType, createBtcSignRequest, createEthSignRequest } from './registry';

const REQUEST_ID = '123e4567-e89b-12d3-a456-426614174000';
const MESSAGE = 'Hardware wallet compatibility fixture';
const FINGERPRINT = 'a1b2c3d4';
const ORIGIN = 'TestApp';
const TESTNET_BTC_ADDRESS = `tb1q${'a'.repeat(38)}`;

const ETH_REQUEST_CBOR =
  'a701d82550123e4567e89b12d3a45642661417400002582548617264776172652077616c6c657420636f6d7061746962696c69747920666978747572650303041a00014a3405d90130a2018a182cf5183cf500f500f400f4021aa1b2c3d406541111111111111111111111111111111111111111076754657374417070';
const ETH_REQUEST_UR =
  'ur:eth-sign-request/osadtpdagdbgfmfeiovsndbgteoxhffwiybbchfzaeaohddafdhsjpiekthsjpihcxkthsjzjzihjycxiajljnjohsjyinidinjzinjykkcxiyinksjykpjpihaxaxaacyaeadgeeeahtaaddyoeadlecsdwykcsfnykaeykaewkaewkaocyoyprsrtyamghbybybybybybybybybybybybybybybybybybybybyatioghihjkjyfpjojosroyleps';
const BTC_REQUEST_CBOR =
  'a601d82550123e4567e89b12d3a45642661417400002582548617264776172652077616c6c657420636f6d7061746962696c697479206669787475726503010481d90130a2018a1854f501f500f500f400f4021aa1b2c3d40581782a746231716161616161616161616161616161616161616161616161616161616161616161616161616161066754657374417070';
const BTC_REQUEST_UR =
  'ur:btc-sign-request/oladtpdagdbgfmfeiovsndbgteoxhffwiybbchfzaeaohddafdhsjpiekthsjpihcxkthsjzjzihjycxiajljnjohsjyinidinjzinjykkcxiyinksjykpjpihaxadaalytaaddyoeadlecsghykadykaeykaewkaewkaocyoyprsrtyahlyksdrjyidehjshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshshsamioghihjkjyfpjojoecrycfjp';
const ETH_SIGNATURE_UR =
  'ur:eth-signature/otadtpdagdbgfmfeiovsndbgteoxhffwiybbchfzaeaohdfpbybybybybybybybybybybybybybybybybybybybybybybybybybybybybybybybycpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcpcwaxisgrihkkjkjyjljtihjtgeiaae';
const BTC_SIGNATURE_UR =
  'ur:btc-signature/otadtpdagdbgfmfeiovsndbgteoxhffwiybbchfzaeaohdfpcteoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoeoaxhdclaofyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfyfycntnutao';

describe('Keystone UR compatibility', () => {
  it('matches the neutral Ethereum sign-request fixture', () => {
    const request = createEthSignRequest(
      Buffer.from(MESSAGE, 'utf8'),
      EthDataType.personalMessage,
      "m/44'/60'/0'/0/0",
      FINGERPRINT,
      REQUEST_ID,
      84532,
      '0x1111111111111111111111111111111111111111',
      ORIGIN,
    );

    expect(request.toCBOR().toString('hex')).toBe(ETH_REQUEST_CBOR);
    expect(request.toUREncoder(400).nextPart()).toBe(ETH_REQUEST_UR);
  });

  it('matches the neutral Bitcoin sign-request fixture', () => {
    const request = createBtcSignRequest(
      REQUEST_ID,
      [FINGERPRINT],
      Buffer.from(MESSAGE, 'utf8'),
      BtcDataType.message,
      ["m/84'/1'/0'/0/0"],
      [TESTNET_BTC_ADDRESS],
      ORIGIN,
    );

    expect(request.toCBOR().toString('hex')).toBe(BTC_REQUEST_CBOR);
    expect(request.toUREncoder(400).nextPart()).toBe(BTC_REQUEST_UR);
  });

  it('refuses mainnet Bitcoin addresses and derivation paths', () => {
    expect(encodeBitcoinMessage(`bc1q${'a'.repeat(38)}`, MESSAGE, "m/84'/0'/0'/0/0", FINGERPRINT)).toBeNull();
    expect(encodeBitcoinMessage(TESTNET_BTC_ADDRESS, MESSAGE, "m/84'/0'/0'/0/0", FINGERPRINT)).toBeNull();
    expect(encodeBitcoinMessage(TESTNET_BTC_ADDRESS, MESSAGE, "m/84'/1'/0'/0/0", FINGERPRINT)).not.toBeNull();
  });

  it('decodes Ethereum message signatures', () => {
    const expected = `0x${'11'.repeat(32)}${'22'.repeat(32)}1b`;
    expect(decodeKeystoneMessageSignature(ETH_SIGNATURE_UR)).toBe(expected);
  });

  it('decodes Bitcoin message signatures', () => {
    const expected = Buffer.concat([Buffer.from([0x1f]), Buffer.alloc(64, 0x33)]).toString('base64');
    expect(decodeKeystoneMessageSignature(BTC_SIGNATURE_UR)).toBe(expected);
  });
});
