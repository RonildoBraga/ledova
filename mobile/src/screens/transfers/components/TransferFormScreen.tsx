import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { GradientBackground } from '../../../components/GradientBackground';
import { Panel } from '../../../components/panel';
import { ButtonGroup } from '../../../components/buttons';
import { QRScanner } from '../../../components/qr';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import {
  getChainShortCode,
  isBitcoinChain,
  isEthereumChain,
  normalizeBitcoinRawTransactionHex,
  WALLET_TYPE,
} from '@ledova/shared';
import type { WalletsStackParamList } from '../../../navigation/WalletsStackNavigator';
import { SendForm } from './SendForm';
import { ReviewTransaction } from './ReviewTransaction';
import { SignTransaction } from './SignTransaction';
import { SoftwareSignTransaction } from './SoftwareSignTransaction';
import { BitcoinSignTransaction } from './BitcoinSignTransaction';
import { SuccessModal } from './SuccessModal';
import { encodeEthereumTransaction } from '../../../utils/keystone/urEncoder';
import { decodeKeystoneSignature } from '../../../utils/keystone/urDecoder';
import { useTransfers } from '../useTransfers';

type Props = NativeStackScreenProps<WalletsStackParamList, 'TransferDetails'>;

export function TransferFormScreen({ route, navigation }: Props) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    content: {
      paddingTop: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
    },
    panelContent: {
      flex: 1,
      flexDirection: 'column',
    },
    scrollWrapper: {
      flex: 1,
    },
    placeholderContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: theme.spacing.lg,
      gap: theme.spacing.md,
    },
    placeholderTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      textAlign: 'center',
    },
    placeholderText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      lineHeight: 20,
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
      textAlign: 'center',
    },
    footer: {
      padding: theme.spacing.sm,
      borderTopWidth: 1,
      borderTopColor: theme.colors.border.default,
      backgroundColor: theme.colors.surface.tertiary,
      marginTop: theme.spacing.sm,
      marginHorizontal: -theme.spacing.sm,
      marginBottom: -theme.spacing.md,
      borderBottomLeftRadius: theme.borderRadius.md,
      borderBottomRightRadius: theme.borderRadius.md,
    },
  }));
  const { wallet: routeWallet } = route.params;
  const [showAddressScanner, setShowAddressScanner] = useState(false);
  const [showSignatureScanner, setShowSignatureScanner] = useState(false);
  const [softwareSignTrigger, setSoftwareSignTrigger] = useState(0);
  const [signedHexInput, setSignedHexInput] = useState('');
  const [signedHexError, setSignedHexError] = useState<string | null>(null);
  const isSoftwareWallet = routeWallet?.walletType === WALLET_TYPE.SOFTWARE;

  const {
    step,
    wallet,
    selectedAsset,
    transferableAssets,
    toAddress,
    amount,
    transactionData,
    txHash,
    isLoadingHoldings,
    isPreparing,
    prepareError,
    broadcastError,
    selectWallet,
    selectAsset,
    setToAddress,
    setAmount,
    useMaxAmount,
    submitTransfer,
    proceedToSign,
    handleSignature,
    backToReview,
    reset,
  } = useTransfers();

  // Initialize the hook with the wallet from route params
  useEffect(() => {
    if (routeWallet) {
      selectWallet(routeWallet);
    }
  }, [routeWallet, selectWallet]);

  const chainShortName = wallet ? getChainShortCode(wallet.chain) : 'ETH';
  const isEthereum = isEthereumChain(chainShortName);
  const isBitcoin = isBitcoinChain(chainShortName);
  const canSubmit = !!toAddress && !!amount && !!selectedAsset && !isPreparing;

  // Encode transaction as UR for QR display
  const urEncodedTransaction = useMemo(() => {
    if (!transactionData || !wallet || !isEthereum) return null;

    try {
      const encoded = encodeEthereumTransaction(
        wallet.address,
        transactionData.transaction as unknown as Parameters<typeof encodeEthereumTransaction>[1],
        wallet.derivationPath,
        wallet.masterFingerprint,
      );
      return encoded?.urString || null;
    } catch {
      return null;
    }
  }, [transactionData, wallet, isEthereum]);

  const handleOpenAddressScanner = useCallback(() => {
    setShowAddressScanner(true);
  }, []);

  const handleCloseAddressScanner = useCallback(() => {
    setShowAddressScanner(false);
  }, []);

  const handleAddressScan = useCallback(
    (data: string) => {
      setToAddress(data);
      setShowAddressScanner(false);
    },
    [setToAddress],
  );

  const handleOpenSignatureScanner = useCallback(() => {
    setShowSignatureScanner(true);
  }, []);

  const handleCloseSignatureScanner = useCallback(() => {
    setShowSignatureScanner(false);
  }, []);

  const handleSignatureScan = useCallback(
    (data: string) => {
      if (!transactionData?.transaction) return;

      const signedTx = decodeKeystoneSignature(
        data,
        transactionData.transaction as unknown as Parameters<typeof decodeKeystoneSignature>[1],
      );
      if (signedTx) {
        handleSignature(signedTx);
        setShowSignatureScanner(false);
      }
    },
    [handleSignature, transactionData],
  );

  const handleSignedHexChange = useCallback((value: string) => {
    setSignedHexInput(value);
    setSignedHexError(null);
  }, []);

  // Bitcoin: the user signed elsewhere; validate the pasted hex and hand it to the broadcast step
  const handleBroadcastSignedHex = useCallback(() => {
    const normalized = normalizeBitcoinRawTransactionHex(signedHexInput);
    if (!normalized) {
      setSignedHexError('Enter the signed raw transaction as hex (whole bytes; an optional 0x prefix is removed).');
      return;
    }
    setSignedHexError(null);
    handleSignature(normalized);
  }, [signedHexInput, handleSignature]);

  // Handle back navigation based on current step
  const handleBack = useCallback(() => {
    if (step === 'review') {
      reset();
      if (routeWallet) selectWallet(routeWallet);
    } else if (step === 'sign') {
      backToReview();
    } else {
      navigation.goBack();
    }
  }, [step, reset, routeWallet, selectWallet, backToReview, navigation]);

  const handleDone = useCallback(() => {
    reset();
    navigation.goBack();
  }, [reset, navigation]);

  const renderContent = () => {
    // Waiting for wallet to be set in hook
    if (!wallet || step === 'select-wallet') {
      return (
        <View style={styles.placeholderContainer}>
          <ActivityIndicator size="small" color={theme.colors.interactive.active} />
          <Text style={styles.placeholderText}>Loading wallet...</Text>
        </View>
      );
    }

    switch (step) {
      case 'enter-details':
        return (
          <SendForm
            chainShortName={chainShortName}
            walletName={wallet.name || ''}
            walletAddress={wallet.address}
            selectedAsset={selectedAsset}
            transferableAssets={transferableAssets}
            toAddress={toAddress}
            amount={amount}
            isLoadingHoldings={isLoadingHoldings}
            prepareError={prepareError}
            selectAsset={selectAsset}
            setToAddress={setToAddress}
            setAmount={setAmount}
            useMaxAmount={useMaxAmount}
            onOpenAddressScanner={handleOpenAddressScanner}
          />
        );

      case 'review':
        if (!transactionData) return null;
        return <ReviewTransaction transactionData={transactionData} chainShortName={chainShortName} />;

      case 'sign':
        if (isBitcoin) {
          if (!transactionData) return null;
          return (
            <BitcoinSignTransaction
              transactionData={transactionData}
              signedHex={signedHexInput}
              onChangeSignedHex={handleSignedHexChange}
              error={signedHexError}
            />
          );
        }
        if (wallet.walletType === WALLET_TYPE.SOFTWARE) {
          if (!transactionData) return null;
          return (
            <SoftwareSignTransaction
              wallet={wallet}
              transactionData={transactionData}
              onSignComplete={handleSignature}
              signTrigger={softwareSignTrigger}
            />
          );
        }
        return <SignTransaction urEncodedTransaction={urEncodedTransaction} />;

      case 'broadcast':
        return (
          <View style={styles.placeholderContainer}>
            {!broadcastError && <ActivityIndicator size="small" color={theme.colors.interactive.active} />}
            <Text style={styles.placeholderTitle}>Broadcasting Transaction</Text>
            {!broadcastError && (
              <Text style={styles.placeholderText}>Submitting your transaction to the network...</Text>
            )}
            {broadcastError && <Text style={styles.errorText}>{broadcastError}</Text>}
          </View>
        );

      case 'success':
        return (
          <SuccessModal visible={true} txHash={txHash || null} chainShortName={chainShortName} onDone={handleDone} />
        );

      default:
        return null;
    }
  };

  const renderFooter = () => {
    // These steps handle their own UI
    if (step === 'success' || step === 'select-wallet') return null;
    if (!wallet) return null;

    // A failed broadcast keeps the error on screen; Back returns to the review step
    if (step === 'broadcast') {
      if (!broadcastError) return null;
      return (
        <View style={styles.footer}>
          <ButtonGroup primaryButton={{ label: 'Back', onPress: backToReview }} size="medium" />
        </View>
      );
    }

    if (step === 'enter-details') {
      return (
        <View style={styles.footer}>
          <ButtonGroup
            primaryButton={{
              label: 'Continue',
              onPress: submitTransfer,
              disabled: !canSubmit,
              loading: isPreparing,
            }}
            size="medium"
          />
        </View>
      );
    }

    if (step === 'review') {
      return (
        <View style={styles.footer}>
          <ButtonGroup
            secondaryButton={{
              label: 'Back',
              onPress: handleBack,
            }}
            primaryButton={{
              label: 'Sign',
              onPress: proceedToSign,
            }}
            size="medium"
          />
        </View>
      );
    }

    if (step === 'sign') {
      return (
        <View style={styles.footer}>
          <ButtonGroup
            secondaryButton={{
              label: 'Back',
              onPress: backToReview,
            }}
            primaryButton={
              isBitcoin
                ? {
                    label: 'Broadcast',
                    onPress: handleBroadcastSignedHex,
                    disabled: signedHexInput.trim().length === 0,
                  }
                : isSoftwareWallet
                  ? {
                      label: 'Sign & Send',
                      onPress: () => setSoftwareSignTrigger((prev) => prev + 1),
                    }
                  : {
                      label: 'Scan Signature',
                      onPress: handleOpenSignatureScanner,
                    }
            }
            size="medium"
          />
        </View>
      );
    }

    return null;
  };

  return (
    <GradientBackground>
      <View style={styles.container}>
        <View style={styles.content}>
          <Panel fullHeight={true}>
            <View style={styles.panelContent}>
              <View style={styles.scrollWrapper}>{renderContent()}</View>
              {renderFooter()}
            </View>
          </Panel>
        </View>
      </View>

      <QRScanner
        visible={showAddressScanner}
        onClose={handleCloseAddressScanner}
        onScan={handleAddressScan}
        title="Scan Destination Address"
        subtitle="Scan the QR code of the destination wallet address"
      />

      {/* Signature QR Scanner (EVM hardware wallets only) */}
      {!isSoftwareWallet && !isBitcoin && (
        <QRScanner
          visible={showSignatureScanner}
          onClose={handleCloseSignatureScanner}
          onScan={handleSignatureScan}
          title="Scan Signed Transaction"
          subtitle="Scan the signature QR code from your hardware wallet"
        />
      )}
    </GradientBackground>
  );
}
