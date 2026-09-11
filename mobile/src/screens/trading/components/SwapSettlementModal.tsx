import React from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View } from 'react-native';
import { formatUnits } from 'ethers';
import { swapSettlementAdmitted, type SwapSettlement, type Wallet } from '@ledova/shared';
import { CustomModal } from '../../../components/modal';
import { QRDisplay, QRScanner } from '../../../components/qr';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useSwapSettlementSigning } from '../useSwapSettlementSigning';

interface Props {
  settlement: SwapSettlement;
  wallet: Wallet | null;
  visible?: boolean;
  onClose: () => void;
}

export function SwapSettlementModal({ settlement, wallet, visible = true, onClose }: Props) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    content: { gap: theme.spacing.md },
    title: { color: theme.colors.text.primary, fontSize: theme.fontSize.lg, fontWeight: theme.fontWeight.semibold },
    text: { color: theme.colors.text.secondary, fontSize: theme.fontSize.sm },
    button: { color: theme.colors.interactive.default, fontSize: theme.fontSize.sm },
  }));
  const signing = useSwapSettlementSigning(settlement, wallet, visible);
  const { state, view } = signing;
  const response = state.response;
  const context = response?.swapOrder.settlementContext;
  const current = signing.isCurrent();
  const idle = ['ready', 'approval-ready', 'error'].includes(state.phase);
  const admitted = current && response && swapSettlementAdmitted(response);
  const close = () => {
    signing.close();
    onClose();
  };
  const run = (operation: () => Promise<void>) => {
    if (signing.isCurrent()) void operation();
  };
  const approve = state.approvalData?.needsApproval && state.phase === 'approval-ready';
  const allowanceSufficient =
    state.approvalStatus?.needsApproval === false || state.approvalData?.needsApproval === false;
  const canSign = admitted && state.phase === 'ready' && allowanceSufficient;
  const confirm =
    view.step === 'show' ? signing.scan : approve || canSign ? () => void signing.start(!!approve) : undefined;
  return (
    <>
      <CustomModal
        visible={visible && view.step !== 'scan'}
        onClose={close}
        showFooter
        showCancelButton
        cancelLabel="Close"
        onCancel={close}
        onConfirm={current ? confirm : undefined}
        confirmLabel={view.step === 'show' ? "I've signed it" : approve ? 'Sign token approval' : 'Sign settlement'}
      >
        <View style={styles.content}>
          <Text style={styles.title}>Review settlement</Text>
          {!current && (
            <Text style={styles.text}>This signing view has ended. Close it and check the saved settlement again.</Text>
          )}
          {!idle && <ActivityIndicator color={theme.colors.interactive.default} />}
          {context && response && (
            <>
              <Text style={styles.text}>
                Token: {context.shareToken.symbol} — {context.shareToken.name}
              </Text>
              <Text style={styles.text}>
                Shares: {formatUnits(response.typedData.message.shareAmount, context.shareToken.decimals)}
              </Text>
              <Text style={styles.text}>
                Payment:{' '}
                {formatUnits(response.typedData.message.paymentAmount, context.paymentAsset.deploymentDecimals)}{' '}
                {context.paymentAsset.symbol}
              </Text>
              <Text style={styles.text}>
                Price per share: {context.pricePerShare} {context.paymentAsset.symbol}
              </Text>
              <Text style={styles.text}>Your role: {response.userRole}</Text>
              <Text style={styles.text}>Wallet: {context[response.userRole].address}</Text>
              <Text style={styles.text}>Seller: {context.seller.address}</Text>
              <Text style={styles.text}>Buyer: {context.buyer.address}</Text>
              <Text style={styles.text}>Network: {response.typedData.domain.chainId}</Text>
              <Text style={styles.text}>Settlement contract: {response.typedData.domain.verifyingContract}</Text>
              <Text style={styles.text}>Share token: {context.shareToken.address}</Text>
              <Text style={styles.text}>Payment token: {context.paymentAsset.deploymentAddress}</Text>
              <Text style={styles.text}>Signing deadline: {response.swapOrder.expiresAt}</Text>
              <Text style={styles.text}>Current status: {response.swapOrder.status.replaceAll('_', ' ')}</Text>
              <Text style={styles.text}>
                Seller signature: {response.swapOrder.sellerHasSigned ? 'recorded' : 'awaiting'}
              </Text>
              <Text style={styles.text}>
                Buyer signature: {response.swapOrder.buyerHasSigned ? 'recorded' : 'awaiting'}
              </Text>
            </>
          )}
          {approve && state.approvalData?.needsApproval && (
            <>
              <Text style={styles.title}>Unlimited token approval</Text>
              <Text style={styles.text}>Token: {state.approvalData.tokenSymbol}</Text>
              <Text style={styles.text}>Spender: {state.approvalData.spender}</Text>
              <Text style={styles.text}>
                This permits the settlement contract to spend this token without a fixed allowance limit.
              </Text>
            </>
          )}
          {state.unconfirmedApprovalHashes.map((hash) => (
            <View key={hash}>
              <Text style={styles.text}>Approval outcome unconfirmed</Text>
              <Text selectable style={styles.text}>
                {hash}
              </Text>
            </View>
          ))}
          {state.unconfirmedApprovalHashes.length > 0 && (
            <Text style={styles.text}>
              A sufficient allowance can permit signing. It does not confirm these original transactions. No replacement
              approval is sent automatically.
            </Text>
          )}
          {state.approvalResult && !('code' in state.approvalResult) && (
            <Text style={styles.text}>Original approval confirmed: {state.approvalResult.txHash}</Text>
          )}
          {state.error && (
            <Text accessibilityRole="alert" style={styles.text}>
              {state.error}
            </Text>
          )}
          {state.notice && <Text style={styles.text}>{state.notice}</Text>}
          {view.error && (
            <Text accessibilityRole="alert" style={styles.text}>
              {view.error}
            </Text>
          )}
          {view.step === 'show' && view.qr && (
            <>
              <Text style={styles.text}>Scan this signing code with your hardware wallet.</Text>
              <QRDisplay data={view.qr} isUR />
              <TouchableOpacity accessibilityRole="button" onPress={signing.back}>
                <Text style={styles.button}>Back to review</Text>
              </TouchableOpacity>
            </>
          )}
          {current && idle && view.step === 'review' && (
            <>
              <TouchableOpacity accessibilityRole="button" onPress={() => run(settlement.recover)}>
                <Text style={styles.button}>Check settlement status</Text>
              </TouchableOpacity>
              {admitted && (
                <TouchableOpacity accessibilityRole="button" onPress={() => run(settlement.refreshApprovalStatus)}>
                  <Text style={styles.button}>Check token approval</Text>
                </TouchableOpacity>
              )}
              {admitted &&
                state.approvalStatus?.needsApproval &&
                !state.unconfirmedApprovalHashes.length &&
                !approve && (
                  <TouchableOpacity accessibilityRole="button" onPress={() => run(settlement.prepareApproval)}>
                    <Text style={styles.button}>Review token approval</Text>
                  </TouchableOpacity>
                )}
            </>
          )}
          <Text style={styles.text}>
            You can close and check saved settlements later. Signing and sending always require a fresh review.
          </Text>
        </View>
      </CustomModal>
      <QRScanner
        visible={visible && current && view.step === 'scan'}
        onClose={signing.back}
        onScan={(text) => void signing.onScan(text)}
        title={view.approval ? 'Scan approval signature' : 'Scan settlement signature'}
        subtitle="Scan the signature for the exact details you just reviewed."
      />
    </>
  );
}
