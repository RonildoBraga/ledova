import { URDecoder } from '@ngraveio/bc-ur';
import { Transaction, Signature } from 'ethers';
import { decodeBtcSignature, decodeEthSignature } from './registry';

export function decodeKeystoneSignedTransaction(
  urSignatureString: string,
  unsignedTx?: {
    to: string;
    value: string;
    gas: string;
    gasPrice: string;
    nonce: string;
    data: string;
    chainId: string;
  },
): string | null {
  try {
    const decoder = new URDecoder();
    decoder.receivePart(urSignatureString.toLowerCase());

    if (!decoder.isComplete()) {
      return null;
    }

    const ur = decoder.resultUR();

    if (ur.type === 'eth-signature') {
      const sigBuffer = decodeEthSignature(ur.cbor);

      if (sigBuffer.length >= 65 && sigBuffer.length < 100 && unsignedTx) {
        const r = '0x' + sigBuffer.subarray(0, 32).toString('hex');
        const s = '0x' + sigBuffer.subarray(32, 64).toString('hex');

        let v: number;
        if (sigBuffer.length === 66) {
          v = (sigBuffer[64] << 8) | sigBuffer[65];
        } else {
          const vRaw = sigBuffer[64];

          const chainId = parseInt(unsignedTx.chainId, 16);
          if (vRaw === 0 || vRaw === 1) {
            v = chainId * 2 + 35 + vRaw;
          } else {
            v = vRaw;
          }
        }

        const chainId = parseInt(unsignedTx.chainId, 16);

        const txParams = {
          to: unsignedTx.to,
          value: BigInt(unsignedTx.value),
          gasLimit: BigInt(unsignedTx.gas),
          gasPrice: BigInt(unsignedTx.gasPrice),
          nonce: parseInt(unsignedTx.nonce, 16),
          data: unsignedTx.data,
          chainId: chainId,
          type: 0,
          signature: Signature.from({ r, s, v }),
        };

        const tx = Transaction.from(txParams);

        return tx.serialized;
      }

      if (sigBuffer.length >= 100) {
        return '0x' + sigBuffer.toString('hex');
      }
    }

    return null;
  } catch {
    return null;
  }
}

export function decodeKeystoneMessageSignature(urSignatureString: string): string | null {
  try {
    const decoder = new URDecoder();
    decoder.receivePart(urSignatureString.toLowerCase());

    if (!decoder.isComplete()) {
      return null;
    }

    const ur = decoder.resultUR();

    if (ur.type === 'eth-signature') {
      const signatureBuffer = decodeEthSignature(ur.cbor);

      if (signatureBuffer.length !== 65) {
        return null;
      }

      return '0x' + signatureBuffer.toString('hex');
    } else if (ur.type === 'btc-signature') {
      const signatureBuffer = decodeBtcSignature(ur.cbor);

      return signatureBuffer.toString('base64');
    } else {
      return null;
    }
  } catch {
    return null;
  }
}
