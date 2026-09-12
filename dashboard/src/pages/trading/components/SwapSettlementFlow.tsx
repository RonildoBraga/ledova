import { useEffect, useMemo, useReducer, useRef, useSyncExternalStore } from 'react';
import { AnimatedQRCode } from '@keystonehq/animated-qr';
import { getNumber } from 'ethers';
import { WALLET_VERIFICATION_STATUS, type SwapSettlement, type Wallet } from '@ledova/shared';
import { Modal } from '@components/Modal';
import { SeedPhraseInput } from '@components/SeedPhraseInput';
import { QRScannerView, useQRScanner } from '@components/qr';
import {
  approvalTransactionForSigning,
  exactSettlementAmount,
  settlementWalletKey,
  swapSettlementCrypto,
} from '@services/swapSettlements';
import { encodeEthereumTransaction, encodeEthereumTypedData } from '@utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature, decodeKeystoneSignedTransaction } from '@utils/keystone/urDecoder';
import {
  DEFAULT_EVM_DERIVATION_PATH,
  deriveAddress,
  signEthereumTransaction,
  signEthereumTypedData,
} from '@utils/softwareWallet/localSigner';

interface Props {
  settlement: SwapSettlement;
  wallets: Wallet[];
  onClose: () => void;
}

export function SwapSettlementFlow({ settlement, wallets, onClose }: Props) {
  const state = useSyncExternalStore(settlement.subscribe, settlement.getSnapshot, settlement.getSnapshot);
  const response = state.response;
  const context = response?.swapOrder.settlementContext;
  const party = response && context ? context[response.userRole] : null;
  const wallet =
    wallets.find(
      (candidate) =>
        candidate.uuid === response?.walletUuid &&
        candidate.userAccount === response.ownerAccountUuid &&
        candidate.address.toLowerCase() === party?.address.toLowerCase() &&
        candidate.verificationStatus === WALLET_VERIFICATION_STATUS.VERIFIED,
    ) ?? null;
  const walletKey = settlementWalletKey(wallet);
  const [, render] = useReducer((value: number) => value + 1, 0);
  const view = useMemo(
    () => ({
      closed: false,
      step: 'review' as 'review' | 'software' | 'qr' | 'scan',
      kind: 'signature' as 'signature' | 'approval',
      seedPhrase: '',
      error: null as string | null,
      qr: null as { cborHex: string; type: string; attempt: number } | null,
    }),
    [settlement, walletKey],
  );
  const activeView = useRef(view);
  activeView.current = view;
  useEffect(() => {
    view.closed = false;
    return () => {
      view.closed = true;
      view.seedPhrase = '';
      view.qr = null;
    };
  }, [view]);
  const current = () => !view.closed && activeView.current === view && settlement.isCurrent();
  const idle = () =>
    current() &&
    state.attempt === settlement.getSnapshot().attempt &&
    ['ready', 'approval-ready'].includes(settlement.getSnapshot().phase);
  const approval = state.approvalData?.needsApproval ? state.approvalData.transaction : null;
  const software = wallet?.signingPreference === 'software' || (!wallet?.derivationPath && !wallet?.masterFingerprint);
  const canSign = !!response?.canSign && !response.hasSigned && !!wallet;
  const ready = ['ready', 'approval-ready'].includes(state.phase);
  const reviewedQr = view.qr;
  const liveQr = !!reviewedQr && reviewedQr.attempt === state.attempt;

  const begin = (kind: 'signature' | 'approval') => {
    if (!idle() || !canSign || !wallet || !response) return;
    if (kind === 'signature' && state.approvalStatus?.needsApproval !== false) return;
    if (kind === 'approval' && !approval) return;
    view.error = null;
    view.seedPhrase = '';
    view.kind = kind;
    if (software) {
      view.step = 'software';
      render();
      return;
    }
    try {
      const encoded =
        kind === 'approval'
          ? encodeEthereumTransaction(
              approval!,
              wallet.derivationPath || undefined,
              wallet.masterFingerprint || undefined,
            )
          : encodeEthereumTypedData(
              wallet.address,
              response.typedData,
              wallet.derivationPath || undefined,
              wallet.masterFingerprint || undefined,
              getNumber(BigInt(response.typedData.domain.chainId)),
            );
      if (!current()) return;
      if (encoded) {
        view.qr = { cborHex: encoded.cborHex, type: encoded.type, attempt: state.attempt };
        view.step = 'qr';
      } else view.error = 'The signing code could not be prepared for this wallet.';
    } catch {
      view.error = 'The signing code could not be prepared for this wallet.';
    }
    render();
  };

  const signSoftware = () => {
    if (!idle() || !canSign || !wallet || view.step !== 'software') return;
    const phrase = view.seedPhrase.trim();
    const path = wallet.derivationPath || DEFAULT_EVM_DERIVATION_PATH;
    view.seedPhrase = '';
    view.step = 'review';
    render();
    const check = (isCurrent: () => boolean) => {
      if (!phrase || !current() || !isCurrent()) return false;
      if (deriveAddress(phrase, path).toLowerCase() !== wallet.address.toLowerCase()) {
        view.error = 'Seed phrase does not match this wallet address.';
        render();
        return false;
      }
      return current() && isCurrent();
    };
    if (view.kind === 'approval') {
      void settlement.signApproval(async (transaction, isCurrent) => {
        if (!check(isCurrent)) return null;
        const signed = await signEthereumTransaction(phrase, path, approvalTransactionForSigning(transaction));
        return current() && isCurrent() ? signed : null;
      });
    } else {
      void settlement.sign(async (typed, isCurrent) => {
        if (!check(isCurrent)) return null;
        const signature = await signEthereumTypedData(
          phrase,
          path,
          typed.domain,
          { SwapOrder: typed.types.SwapOrder },
          { ...typed.message },
        );
        return current() && isCurrent() ? { signature, signerAddress: wallet.address } : null;
      });
    }
  };

  const { error: scannerError, stopScanner } = useQRScanner({
    scannerId: 'swap-settlement-signature',
    enabled: ready && current() && view.step === 'scan' && liveQr,
    onScanSuccess: (text) => {
      if (!idle() || view.step !== 'scan' || !liveQr || view.qr !== reviewedQr || !wallet) return;
      if (view.kind === 'approval') {
        if (!approval) return;
        const signed = decodeKeystoneSignedTransaction(text, approval);
        if (signed && current()) void settlement.broadcastApproval(signed);
      } else {
        const signature = decodeKeystoneMessageSignature(text);
        if (!signature || !response) return;
        void (async () => {
          try {
            const signer = await swapSettlementCrypto.recoverSigner(response.typedData, signature);
            if (idle() && current() && view.step === 'scan' && view.qr === reviewedQr)
              await settlement.submitSignature(signature, signer);
          } catch {
            if (!current()) return;
            view.error = 'The signature code could not be verified for this trade.';
            render();
          }
        })();
      }
    },
  });
  const resetView = () => {
    stopScanner();
    view.seedPhrase = '';
    view.qr = null;
    view.error = null;
    view.step = 'review';
    render();
  };
  const close = () => {
    view.closed = true;
    settlement.close();
    resetView();
    onClose();
  };
  const button = 'rounded-lg bg-brand-mid px-4 py-3 font-medium text-white disabled:opacity-50';

  return (
    <Modal isOpen onClose={close} title="Review and sign trade" size="md">
      <div className="space-y-4">
        {response && context && (
          <div className="rounded-lg bg-surface-tertiary p-4 space-y-2">
            <p>You are the {response.userRole}.</p>
            <p>
              Shares: {exactSettlementAmount(response.typedData.message.shareAmount, context.shareToken.decimals)}{' '}
              {context.shareToken.symbol} — {context.shareToken.name}
            </p>
            <p>
              Payment:{' '}
              {exactSettlementAmount(response.typedData.message.paymentAmount, context.paymentAsset.deploymentDecimals)}{' '}
              {context.paymentAsset.symbol}
            </p>
            <p>Price per share: {context.pricePerShare}</p>
            <p>
              Network: {context.shareToken.chain} ({response.typedData.domain.chainId})
            </p>
            <p className="break-all">Wallet: {party?.address}</p>
            <p>Signing deadline: {new Date(response.swapOrder.expiresAt).toLocaleString()}</p>
          </div>
        )}
        {!ready && state.phase !== 'error' && (
          <p role="status">
            {state.phase === 'loading'
              ? 'Loading the saved trade...'
              : ['submitting', 'approval-submitting'].includes(state.phase)
                ? 'Submitting. You can close and check the saved status later.'
                : 'Checking or signing this trade...'}
          </p>
        )}
        {state.error && <p role="alert">{state.error}</p>}
        {state.notice && <p role="status">{state.notice}</p>}
        {view.error && <p role="alert">{view.error}</p>}
        {state.approvalResult && (
          <div role="status" className="space-y-2">
            <p>
              {'code' in state.approvalResult
                ? 'The approval result is still unknown. Its transaction is saved for checking; do not send it again.'
                : 'Approval confirmed.'}
            </p>
            <p className="break-all">Approval transaction: {state.approvalResult.txHash}</p>
          </div>
        )}
        {state.unconfirmedApprovalHashes.length > 0 && (
          <div role="status" className="space-y-2">
            <p>
              Earlier approval transactions remain saved for checking, even if the token allowance is now sufficient.
            </p>
            {state.unconfirmedApprovalHashes.map((hash) => (
              <p className="break-all" key={hash}>
                {hash}
              </p>
            ))}
          </div>
        )}
        {response?.hasSigned && (
          <p role="status">Your signature is recorded. Trade status: {response.swapOrder.status}.</p>
        )}
        {response && !response.hasSigned && !response.canSign && (
          <p>This trade is unavailable for a new signature. Its saved details remain available to check.</p>
        )}
        {response && !wallet && <p>The exact verified wallet is unavailable in the current account.</p>}
        {approval && response && (
          <div className="space-y-2">
            <p>This token approval has no spending limit.</p>
            <p className="break-all">Approved contract: {response.typedData.domain.verifyingContract}</p>
          </div>
        )}
        {ready && canSign && view.step === 'review' && (
          <div className="flex flex-wrap gap-3">
            <button
              className={button}
              onClick={() => {
                resetView();
                void settlement.refreshApprovalStatus();
              }}
            >
              Check token approval
            </button>
            {state.approvalStatus?.needsApproval && (
              <button
                className={button}
                onClick={() => {
                  resetView();
                  void settlement.prepareApproval();
                }}
              >
                Prepare approval
              </button>
            )}
            {approval && (
              <button className={button} onClick={() => begin('approval')}>
                Continue to approve
              </button>
            )}
            {state.approvalStatus?.needsApproval === false && (
              <button className={button} onClick={() => begin('signature')}>
                Continue to sign
              </button>
            )}
          </div>
        )}
        {ready && canSign && view.step === 'software' && (
          <>
            <SeedPhraseInput
              value={view.seedPhrase}
              onChange={(value) => {
                if (!current()) return;
                view.seedPhrase = value;
                render();
              }}
            />
            <button className={button} disabled={!view.seedPhrase.trim()} onClick={signSoftware}>
              {view.kind === 'approval' ? 'Sign approval' : 'Sign trade'}
            </button>
          </>
        )}
        {ready && canSign && view.step === 'qr' && liveQr && view.qr && (
          <>
            <div className="flex justify-center bg-white p-4">
              <AnimatedQRCode cbor={view.qr.cborHex} type={view.qr.type} />
            </div>
            <button
              className={button}
              onClick={() => {
                if (!idle() || !liveQr) return;
                view.step = 'scan';
                render();
              }}
            >
              I&apos;ve signed it
            </button>
          </>
        )}
        {ready && view.step === 'scan' && liveQr && (
          <QRScannerView scannerId="swap-settlement-signature" error={scannerError} />
        )}
        {ready && view.step !== 'review' && (
          <button className={button} onClick={resetView}>
            Back
          </button>
        )}
        {(state.phase === 'error' || response?.hasSigned || (response && !response.canSign)) && (
          <button
            className={button}
            onClick={() => {
              resetView();
              void settlement.recover();
            }}
          >
            Check saved status
          </button>
        )}
        <button className={button} onClick={close}>
          Close
        </button>
      </div>
    </Modal>
  );
}
