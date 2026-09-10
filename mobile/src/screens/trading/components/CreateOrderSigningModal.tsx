import React, { useEffect, useRef } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import {
  getWalletVerificationEvmChainId,
  useOrderSubmissionSigning,
  type OrderSubmission,
  type TransferOrder,
  type Wallet,
  type ShareToken,
  formatWalletAddressShort,
} from '@ledova/shared';
import { CustomModal } from '../../../components/modal';
import { QRDisplay, QRScanner } from '../../../components/qr';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { getSeedPhrase } from '../../../services/secureKeyStorage';
import { signEthereumTypedData } from '../../../utils/softwareWallet/localSigner';
import { encodeEthereumTypedData } from '../../../utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '../../../utils/keystone/urDecoder';

interface Props {
  submission: OrderSubmission;
  wallet: Wallet | null;
  tokens: ShareToken[];
  onClose: () => void;
  onSuccess?: (order: TransferOrder) => void;
}

export function CreateOrderSigningModal({ submission, wallet, tokens, onClose, onSuccess }: Props) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    content: { gap: theme.spacing.md },
    title: { fontSize: theme.fontSize.lg, fontWeight: theme.fontWeight.semibold, color: theme.colors.text.primary },
    text: { fontSize: theme.fontSize.sm, color: theme.colors.text.secondary },
  }));
  const delivered = useRef(false);
  const signing = useOrderSubmissionSigning(submission, wallet, (message, selectedWallet) => {
    const encoded = encodeEthereumTypedData(
      selectedWallet.address,
      { domain: message.domain, types: message.types, message: message.message },
      selectedWallet.derivationPath || undefined,
      selectedWallet.masterFingerprint || undefined,
      getWalletVerificationEvmChainId(selectedWallet.chain) ?? undefined,
    );
    return encoded ? { cborHex: encoded.cbor.toString('hex'), type: encoded.type } : null;
  });
  const { state, view } = signing;
  const token = tokens.find((candidate) => candidate.uuid === state.snapshot?.intent.token);
  useEffect(() => {
    if (state.phase === 'created' && state.snapshot?.order && !delivered.current && submission.isCurrent()) {
      delivered.current = true;
      onSuccess?.(state.snapshot.order);
    }
  }, [state, submission, onSuccess]);
  const close = () => {
    signing.close();
    onClose();
  };
  const confirm = () => {
    if (state.phase === 'error') {
      void submission.recover();
      return;
    }
    if (view.step === 'show-qr') {
      signing.scan();
      return;
    }
    if (wallet?.signingPreference !== 'software') {
      signing.showQr();
      return;
    }
    void signing.sign(async (message, current) => {
      if (!wallet.derivationPath || !wallet.masterFingerprint)
        throw new Error('This wallet is missing its local signing key.');
      if (!current()) return null;
      const mnemonic = await getSeedPhrase(wallet.masterFingerprint);
      if (!mnemonic || !current()) return null;
      return signEthereumTypedData(mnemonic, wallet.derivationPath, message.domain, message.types, message.message);
    });
  };
  const canConfirm =
    state.phase === 'error' || (state.phase === 'ready' && ['instructions', 'show-qr'].includes(view.step));
  return (
    <>
      <CustomModal
        visible={!(state.phase === 'ready' && view.step === 'scan-signature')}
        onClose={close}
        showFooter
        showCancelButton
        cancelLabel={['created', 'refused'].includes(state.phase) ? 'Done' : 'Close'}
        onCancel={close}
        onConfirm={canConfirm ? confirm : undefined}
        confirmDisabled={state.phase === 'ready' && !signing.walletReady}
        confirmLabel={
          state.phase === 'error'
            ? 'Check order status'
            : view.step === 'show-qr'
              ? "I've signed it"
              : wallet?.signingPreference === 'software'
                ? 'Sign with biometric'
                : 'Show signing code'
        }
      >
        <View style={styles.content}>
          <Text style={styles.title}>{state.recovered ? 'Check saved order' : 'Review order'}</Text>
          {['preparing', 'signing', 'submitting'].includes(state.phase) && (
            <ActivityIndicator color={theme.colors.interactive.default} />
          )}
          {state.phase === 'preparing' && (
            <Text style={styles.text}>Checking order and preparing signing details...</Text>
          )}
          {state.phase === 'signing' && <Text style={styles.text}>Authenticating and signing this order...</Text>}
          {state.phase === 'submitting' && (
            <Text style={styles.text}>
              Submitting this order. You can close this window and check its status from saved orders.
            </Text>
          )}
          {state.phase === 'ready' && (
            <>
              <Text style={styles.text}>
                Token: {token ? `${token.symbol} — ${token.name}` : state.snapshot?.intent.token}
              </Text>
              <Text style={styles.text}>
                Wallet: {formatWalletAddressShort(state.snapshot?.intent.walletAddress ?? '')}
              </Text>
              <Text style={styles.text}>
                {state.snapshot?.intent.orderType.toUpperCase()} {state.snapshot?.intent.quantity} shares
              </Text>
              <Text style={styles.text}>Price per share: ${state.snapshot?.intent.pricePerShare}</Text>
              <Text style={styles.text}>Minimum fill: {state.snapshot?.intent.minQuantity} shares</Text>
              {!signing.walletReady && (
                <Text style={styles.text}>
                  This wallet is unavailable for signing in the current account. The saved order remains available to
                  check.
                </Text>
              )}
              {view.error && <Text style={styles.text}>{view.error}</Text>}
              {view.step === 'show-qr' && view.qrData && <QRDisplay data={view.qrData.cborHex} isUR />}
            </>
          )}
          {state.phase === 'created' && state.snapshot?.order && (
            <>
              <Text style={styles.title}>{state.recovered ? 'Order recovered' : 'Order created'}</Text>
              <Text style={styles.text}>
                Current status: {state.snapshot.order.statusDisplay ?? state.snapshot.order.status.replaceAll('_', ' ')}
              </Text>
              <Text style={styles.text}>
                {state.snapshot.order.quantity} {state.snapshot.order.tokenSymbol} shares at $
                {state.snapshot.order.pricePerShare}
              </Text>
            </>
          )}
          {state.phase === 'refused' && (
            <>
              <Text style={styles.title}>Order declined</Text>
              <Text style={styles.text}>{state.snapshot?.refusal?.detail}</Text>
              <Text style={styles.text}>A new order requires a new review and signature.</Text>
            </>
          )}
          {state.phase === 'error' && (
            <>
              <Text style={styles.title}>Order status unconfirmed</Text>
              <Text style={styles.text}>{state.error}</Text>
              <Text style={styles.text}>
                This order remains saved. Check its status before signing again. An unavailable result does not start a
                replacement order.
              </Text>
            </>
          )}
          {state.notice && <Text style={styles.text}>{state.notice}</Text>}
        </View>
      </CustomModal>
      <QRScanner
        visible={state.phase === 'ready' && view.step === 'scan-signature'}
        onClose={signing.back}
        onScan={(text) => {
          const signature = decodeKeystoneMessageSignature(text);
          if (signature) void signing.submitSignature(signature);
        }}
        title="Scan order signature"
        subtitle="Scan the signature for the order you just reviewed."
      />
    </>
  );
}
