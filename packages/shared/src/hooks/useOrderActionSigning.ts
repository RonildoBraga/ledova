import { useEffect, useMemo, useReducer, useRef, useSyncExternalStore } from 'react';
import type { OrderActionChallenge, Wallet } from '../types';
import type { OrderAction } from '../utils/order-action';

type QrData = { cborHex: string; type: string };
type Encoder = (message: OrderActionChallenge, wallet: Wallet) => QrData | null;
type Signer = (message: OrderActionChallenge, isCurrent: () => boolean) => Promise<string | null>;

function walletKey(wallet: Wallet | null): string {
  return wallet
    ? [
        wallet.uuid,
        wallet.userAccount,
        wallet.address.toLowerCase(),
        wallet.derivationPath,
        wallet.masterFingerprint,
        wallet.signingPreference,
      ].join('/')
    : '';
}

export function useOrderActionSigning(submission: OrderAction, wallets: Wallet[], encode: Encoder) {
  const state = useSyncExternalStore(submission.subscribe, submission.getSnapshot, submission.getSnapshot);
  const identity = state.snapshot ?? state.context;
  const wallet =
    wallets.find(
      (candidate) =>
        candidate.uuid === identity?.walletUuid &&
        candidate.userAccount === submission.owner.ownerAccountUuid &&
        candidate.address.toLowerCase() === identity.walletAddress.toLowerCase(),
    ) ?? null;
  const [, render] = useReducer((value: number) => value + 1, 0);
  const lifetime = useMemo(() => ({ retired: false }), [submission]);
  const active = useRef(lifetime);
  active.current = lifetime;
  const latestWallet = useRef(wallet);
  latestWallet.current = wallet;
  const view = useMemo(
    () => ({
      step: 'instructions' as 'instructions' | 'software' | 'show-qr' | 'scan-signature',
      qrData: null as QrData | null,
      error: null as string | null,
    }),
    [submission, state.attempt],
  );
  useEffect(() => {
    lifetime.retired = false;
    return () => {
      lifetime.retired = true;
    };
  }, [lifetime]);
  const current = () => !lifetime.retired && active.current === lifetime && submission.isCurrent();
  const ready = () =>
    current() && submission.getSnapshot().attempt === state.attempt && submission.getSnapshot().phase === 'ready';
  const walletReady =
    !!wallet &&
    wallet.uuid === state.snapshot?.walletUuid &&
    wallet.userAccount === submission.owner.ownerAccountUuid &&
    wallet.address.toLowerCase() === state.snapshot?.walletAddress.toLowerCase();

  const showQr = () => {
    if (!ready() || !walletReady || !wallet || !state.challenge) return;
    try {
      const qr = encode(state.challenge, wallet);
      if (!qr) throw new Error('No signing code');
      view.qrData = qr;
      view.step = 'show-qr';
      view.error = null;
    } catch {
      view.error = 'The signing code could not be prepared.';
    }
    render();
  };
  const sign = (signer: Signer): Promise<void> => {
    if (!ready() || !walletReady || !state.challenge) return Promise.resolve();
    const selectedWallet = walletKey(wallet);
    return submission.sign(async (activeSigning) => {
      const signingCurrent = () => current() && activeSigning() && walletKey(latestWallet.current) === selectedWallet;
      if (!signingCurrent()) return null;
      const signature = await signer(state.challenge!, signingCurrent);
      return signingCurrent() ? signature : null;
    });
  };
  const submitSignature = (signature: string): Promise<void> => {
    if (!ready() || !walletReady || walletKey(latestWallet.current) !== walletKey(wallet)) return Promise.resolve();
    return submission.submitSignature(signature);
  };
  const showSoftware = () => {
    if (ready() && walletReady) {
      view.step = 'software';
      render();
    }
  };
  const scan = () => {
    if (ready() && view.step === 'show-qr') {
      view.step = 'scan-signature';
      render();
    }
  };
  const back = () => {
    if (!ready()) return;
    view.step = view.step === 'scan-signature' ? 'show-qr' : 'instructions';
    view.error = null;
    render();
  };
  const close = () => {
    lifetime.retired = true;
    submission.close();
  };
  return { state, view, wallet, walletReady, showQr, showSoftware, scan, sign, submitSignature, back, close };
}
