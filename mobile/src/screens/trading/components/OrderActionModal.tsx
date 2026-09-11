import React from 'react';
import { View, Text, TextInput, ActivityIndicator } from 'react-native';
import { useOrderActionSigning, type OrderAction, type Wallet } from '@ledova/shared';
import { CustomModal } from '../../../components/modal';
import { QRDisplay, QRScanner } from '../../../components/qr';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { getSeedPhrase } from '../../../services/secureKeyStorage';
import { signEthereumTypedData } from '../../../utils/softwareWallet/localSigner';
import { encodeEthereumTypedData } from '../../../utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '../../../utils/keystone/urDecoder';

interface Props {
  action: OrderAction;
  wallets: Wallet[];
  onClose: () => void;
}

export function OrderActionModal({ action, wallets, onClose }: Props) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    content: { gap: theme.spacing.md },
    title: { fontSize: theme.fontSize.lg, fontWeight: theme.fontWeight.semibold, color: theme.colors.text.primary },
    text: { fontSize: theme.fontSize.sm, color: theme.colors.text.secondary },
    input: {
      color: theme.colors.text.primary,
      borderColor: theme.colors.border.default,
      borderWidth: 1,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.sm,
    },
  }));
  const signing = useOrderActionSigning(action, wallets, (message, wallet) => {
    const encoded = encodeEthereumTypedData(
      wallet.address,
      { domain: message.domain, types: message.types, message: message.message },
      wallet.derivationPath || undefined,
      wallet.masterFingerprint || undefined,
      message.domain.chainId,
    );
    return encoded ? { cborHex: encoded.cbor.toString('hex'), type: encoded.type } : null;
  });
  const { state, view, wallet } = signing;
  const label = action.purpose === 'cancel' ? 'cancellation' : 'change';
  const review = state.snapshot?.review ?? state.context;
  const replacements = state.snapshot?.intent.modifications;
  const close = () => {
    signing.close();
    onClose();
  };
  const confirm = () => {
    if (state.phase === 'error') {
      void action.recover();
      return;
    }
    if (state.phase === 'editing') {
      void action.prepare();
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
    ['editing', 'error'].includes(state.phase) ||
    (state.phase === 'ready' && ['instructions', 'show-qr'].includes(view.step));
  const confirmLabel =
    state.phase === 'editing'
      ? `Review ${label}`
      : state.phase === 'error'
        ? action.record
          ? `Check ${label} status`
          : 'Retry order details'
        : view.step === 'show-qr'
          ? "I've signed it"
          : wallet?.signingPreference === 'software'
            ? 'Sign with biometric'
            : 'Show signing code';
  return (
    <>
      <CustomModal
        visible={!(state.phase === 'ready' && view.step === 'scan-signature')}
        onClose={close}
        showFooter
        showCancelButton
        cancelLabel={['applied', 'refused'].includes(state.phase) ? 'Done' : 'Close'}
        onCancel={close}
        onConfirm={canConfirm ? confirm : undefined}
        confirmDisabled={state.phase === 'ready' && !signing.walletReady}
        confirmLabel={confirmLabel}
      >
        <View style={styles.content}>
          <Text style={styles.title}>{action.purpose === 'cancel' ? 'Cancel order' : 'Change order'}</Text>
          {['loading', 'preparing', 'signing', 'submitting'].includes(state.phase) && (
            <ActivityIndicator color={theme.colors.interactive.default} />
          )}
          {state.phase === 'loading' && <Text style={styles.text}>Loading current order details...</Text>}
          {state.phase === 'preparing' && (
            <Text style={styles.text}>Checking this {label} and preparing signing details...</Text>
          )}
          {state.phase === 'signing' && <Text style={styles.text}>Authenticating and signing this {label}...</Text>}
          {state.phase === 'submitting' && (
            <Text style={styles.text}>Submitting this {label}. You can close and check its saved status later.</Text>
          )}
          {review && (
            <>
              <Text style={styles.text}>
                Token: {review.token.symbol} — {review.token.name}
              </Text>
              <Text style={styles.text}>Wallet: {state.snapshot?.walletAddress ?? state.context?.walletAddress}</Text>
              <Text style={styles.text}>Reviewed quantity: {review.currentValues.quantity} shares</Text>
              <Text style={styles.text}>Reviewed minimum: {review.currentValues.minQuantity} shares</Text>
              <Text style={styles.text}>Reviewed price per share: ${review.currentValues.pricePerShare}</Text>
              <Text style={styles.text}>Filled: {review.currentValues.filledQuantity} shares</Text>
            </>
          )}
          {state.phase === 'editing' && (
            <>
              {action.purpose === 'cancel' ? (
                <Text style={styles.text}>Cancel the available remainder of this order.</Text>
              ) : (
                <>
                  <Text style={styles.text}>New quantity</Text>
                  <TextInput
                    accessibilityLabel="New quantity"
                    keyboardType="number-pad"
                    style={styles.input}
                    value={state.values?.quantity ?? ''}
                    onChangeText={(value) => action.edit('quantity', value)}
                  />
                  <Text style={styles.text}>New minimum fill</Text>
                  <TextInput
                    accessibilityLabel="New minimum fill"
                    keyboardType="number-pad"
                    style={styles.input}
                    value={state.values?.minQuantity ?? ''}
                    onChangeText={(value) => action.edit('minQuantity', value)}
                  />
                  <Text style={styles.text}>New price per share</Text>
                  <TextInput
                    accessibilityLabel="New price per share"
                    keyboardType="decimal-pad"
                    style={styles.input}
                    value={state.values?.pricePerShare ?? ''}
                    onChangeText={(value) => action.edit('pricePerShare', value)}
                  />
                </>
              )}
              {state.error && (
                <Text accessibilityRole="alert" style={styles.text}>
                  {state.error}
                </Text>
              )}
            </>
          )}
          {replacements && (
            <>
              <Text style={styles.text}>New quantity: {replacements.quantity} shares</Text>
              <Text style={styles.text}>New minimum fill: {replacements.minQuantity} shares</Text>
              <Text style={styles.text}>New price per share: ${replacements.pricePerShare}</Text>
            </>
          )}
          {state.phase === 'ready' && (
            <>
              {!signing.walletReady && (
                <Text style={styles.text}>
                  This exact wallet is unavailable for signing in the current account. The saved action remains
                  available to check.
                </Text>
              )}
              {view.error && (
                <Text accessibilityRole="alert" style={styles.text}>
                  {view.error}
                </Text>
              )}
              {view.step === 'show-qr' && view.qrData && <QRDisplay data={view.qrData.cborHex} isUR />}
            </>
          )}
          {state.phase === 'applied' && (
            <>
              <Text style={styles.title}>{state.recovered ? 'Original action recovered' : 'Action recorded'}</Text>
              {state.snapshot?.result?.kind === 'cancel' && (
                <Text style={styles.text}>
                  This cancellation changed the order from {state.snapshot.result.fromStatus} to cancelled.
                </Text>
              )}
              {state.snapshot?.result?.kind === 'modify' && (
                <>
                  <Text style={styles.text}>
                    This change is modification {state.snapshot.result.modificationCount}.
                  </Text>
                  {state.snapshot.result.changes.length === 0 && (
                    <Text style={styles.text}>The values were already the requested values.</Text>
                  )}
                  {state.snapshot.result.changes.map((change) => (
                    <Text key={change.field} style={styles.text}>
                      {change.field.replaceAll('_', ' ')}: {change.old} → {change.new}
                    </Text>
                  ))}
                </>
              )}
              <Text style={styles.text}>
                Current order status:{' '}
                {state.snapshot?.order.statusDisplay ?? state.snapshot?.order.status.replaceAll('_', ' ')}
              </Text>
            </>
          )}
          {state.phase === 'refused' && (
            <>
              <Text style={styles.title}>
                {action.purpose === 'cancel' ? 'Cancellation declined' : 'Change declined'}
              </Text>
              <Text style={styles.text}>{state.snapshot?.refusal?.detail}</Text>
              <Text style={styles.text}>This is the recorded result of the original request.</Text>
            </>
          )}
          {state.phase === 'error' && (
            <>
              <Text style={styles.title}>
                {action.record ? 'Action status unconfirmed' : 'Order details unavailable'}
              </Text>
              <Text accessibilityRole="alert" style={styles.text}>
                {state.error}
              </Text>
              {action.record && (
                <Text style={styles.text}>
                  Check the saved action before signing again. An unavailable result does not start a replacement
                  action.
                </Text>
              )}
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
        title="Scan action signature"
        subtitle="Scan the signature for the cancellation or change you just reviewed."
      />
    </>
  );
}
