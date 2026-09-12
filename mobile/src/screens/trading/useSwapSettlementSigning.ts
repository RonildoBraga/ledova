import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { getNumber } from 'ethers';
import { swapSettlementAdmitted, type SwapSettlement, type Wallet } from '@ledova/shared';
import { getSeedPhrase } from '../../services/secureKeyStorage';
import { signEthereumTransaction, signEthereumTypedData } from '../../utils/softwareWallet/localSigner';
import { encodeEthereumTypedData } from '../../utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '../../utils/keystone/urDecoder';
import {
  decodeSettlementApproval,
  encodeSettlementApproval,
  settlementApprovalTransaction,
  settlementWalletMaterial,
  swapSettlementCrypto,
} from '../../services/swapSettlements';

type SigningView = {
  step: 'review' | 'show' | 'scan';
  approval: boolean;
  qr: string | null;
  generation: number;
  error: string | null;
};

export function useSwapSettlementSigning(settlement: SwapSettlement, wallet: Wallet | null, visible: boolean) {
  const state = useSyncExternalStore(settlement.subscribe, settlement.getSnapshot, settlement.getSnapshot);
  const pinned = useRef({ settlement, material: settlementWalletMaterial(wallet), retired: false });
  const latest = useRef({ wallet, visible });
  latest.current = { wallet, visible };
  const [view, setView] = useState<SigningView>({
    step: 'review',
    approval: false,
    qr: null,
    generation: 0,
    error: null,
  });
  const viewRef = useRef(view);
  const isCurrent = () => {
    if (
      !latest.current.visible ||
      pinned.current.material !== settlementWalletMaterial(latest.current.wallet) ||
      pinned.current.settlement !== settlement ||
      !settlement.isCurrent()
    ) {
      pinned.current.retired = true;
      settlement.close();
    }
    return !pinned.current.retired;
  };
  isCurrent();
  useEffect(
    () => () => {
      pinned.current.retired = true;
      settlement.close();
    },
    [settlement],
  );
  const update = (next: Partial<SigningView>) => {
    if (!isCurrent()) return;
    viewRef.current = { ...viewRef.current, ...next, generation: viewRef.current.generation + 1 };
    setView(viewRef.current);
  };
  const close = () => {
    pinned.current.retired = true;
    settlement.close();
  };
  const back = () => {
    if (currentView(view.generation)) update({ step: 'review', qr: null, error: null });
  };
  const currentView = (generation: number) => isCurrent() && viewRef.current.generation === generation;
  const fail = () =>
    update({
      step: 'review',
      qr: null,
      error: 'Signing could not complete. Check the original settlement before continuing.',
    });
  const start = async (approval: boolean) => {
    if (
      !currentView(view.generation) ||
      viewRef.current.step !== 'review' ||
      !wallet ||
      !state.response ||
      !swapSettlementAdmitted(state.response)
    )
      return;
    const live = settlement.getSnapshot();
    if (live.phase !== (approval ? 'approval-ready' : 'ready')) return;
    if (!approval && live.approvalStatus?.needsApproval !== false && live.approvalData?.needsApproval !== false) return;
    update({ error: null });
    const generation = viewRef.current.generation;
    if (!wallet.derivationPath || !wallet.masterFingerprint) {
      fail();
      return;
    }
    if (wallet.signingPreference !== 'software') {
      try {
        if (approval) {
          if (!state.approvalData?.needsApproval) return;
          update({ step: 'show', approval, qr: encodeSettlementApproval(state.approvalData.transaction, wallet) });
        } else {
          const typed = state.response.typedData;
          const code = encodeEthereumTypedData(
            wallet.address,
            typed,
            wallet.derivationPath,
            wallet.masterFingerprint,
            getNumber(BigInt(typed.domain.chainId)),
          );
          if (!code) throw new Error('Signing code unavailable.');
          update({ step: 'show', approval, qr: code.cborHex });
        }
      } catch {
        if (currentView(generation)) fail();
      }
      return;
    }
    const current = (admitted: () => boolean) => currentView(generation) && admitted();
    if (approval) {
      await settlement.signApproval(async (transaction, admitted) => {
        if (!current(admitted)) return null;
        const mnemonic = await getSeedPhrase(wallet.masterFingerprint!);
        if (!mnemonic || !current(admitted)) return null;
        const signed = await signEthereumTransaction(
          mnemonic,
          wallet.derivationPath!,
          settlementApprovalTransaction(transaction),
        );
        return current(admitted) ? signed : null;
      });
    } else {
      await settlement.sign(async (typed, admitted) => {
        if (!current(admitted)) return null;
        const mnemonic = await getSeedPhrase(wallet.masterFingerprint!);
        if (!mnemonic || !current(admitted)) return null;
        const signature = await signEthereumTypedData(
          mnemonic,
          wallet.derivationPath!,
          typed.domain,
          { SwapOrder: typed.types.SwapOrder },
          typed.message,
        );
        if (!current(admitted)) return null;
        const signerAddress = await swapSettlementCrypto.recoverSigner(typed, signature);
        return current(admitted) ? { signature, signerAddress } : null;
      });
    }
  };
  const scan = () => {
    if (currentView(view.generation) && viewRef.current.step === 'show') update({ step: 'scan' });
  };
  const onScan = async (text: string) => {
    const generation = view.generation;
    const attempt = state.attempt;
    const currentScan = () => currentView(generation) && attempt === settlement.getSnapshot().attempt;
    if (view.step !== 'scan' || !currentScan() || !state.response || !swapSettlementAdmitted(state.response)) return;
    try {
      if (view.approval) {
        if (!state.approvalData?.needsApproval) return;
        const raw = decodeSettlementApproval(text, state.approvalData.transaction);
        if (!currentScan()) return;
        update({ step: 'review', qr: null });
        await settlement.broadcastApproval(raw);
      } else {
        const signature = decodeKeystoneMessageSignature(text);
        if (!signature || !/^0x[0-9a-f]{130}$/i.test(signature)) throw new Error('Invalid signing code.');
        const signer = await swapSettlementCrypto.recoverSigner(state.response.typedData, signature);
        if (!currentScan()) return;
        update({ step: 'review', qr: null });
        await settlement.submitSignature(signature, signer);
      }
    } catch {
      if (currentView(generation)) fail();
    }
  };
  return { state, view, isCurrent, close, back, scan, onScan, start };
}
