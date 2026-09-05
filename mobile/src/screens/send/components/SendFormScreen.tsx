import React, { useState, useCallback, useMemo } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { CompositeNavigationProp } from '@react-navigation/native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { Wallet } from '@ledova/shared';
import type { BottomTabParamList } from '../../../navigation/BottomTabNavigator';
import type { SendStackParamList } from '../../../navigation/SendStackNavigator';
import { GradientBackground } from '../../../components/GradientBackground';
import { Panel } from '../../../components/panel';
import { ButtonGroup, SecondaryButton } from '../../../components/buttons';
import { QRScanner } from '../../../components/qr';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { BLOCKCHAIN, getChainShortCode, isBitcoinChain, isEthereumChain, WALLET_TYPE } from '@ledova/shared';
import { SendForm } from '../../transfers/components/SendForm';
import { ReviewTransaction } from '../../transfers/components/ReviewTransaction';
import { SignTransaction } from '../../transfers/components/SignTransaction';
import { SoftwareSignTransaction } from '../../transfers/components/SoftwareSignTransaction';
import { SuccessModal } from '../../transfers/components/SuccessModal';
import { WalletSelectionStep } from './WalletSelectionStep';
import { encodeEthereumTransaction } from '../../../utils/keystone/urEncoder';
import { decodeKeystoneSignature } from '../../../utils/keystone/urDecoder';
import { useTransfers } from '../../transfers/useTransfers';

interface SendFormScreenProps {
  onDone: () => void;
}

type SendNavigation = CompositeNavigationProp<
  NativeStackNavigationProp<SendStackParamList>,
  BottomTabNavigationProp<BottomTabParamList>
>;

export function SendFormScreen({ onDone }: SendFormScreenProps) {
  const theme = useAppTheme();
  const navigation = useNavigation<SendNavigation>();
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
      lineHeight: theme.fontSize.sm * theme.lineHeight.normal,
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
  const [showAddressScanner, setShowAddressScanner] = useState(false);
  const [showSignatureScanner, setShowSignatureScanner] = useState(false);
  const [softwareSignTrigger, setSoftwareSignTrigger] = useState(0);

  const {
    step,
    wallet,
    wallets,
    isLoading,
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

  const isSoftwareWallet = wallet?.walletType === WALLET_TYPE.SOFTWARE;
  const chainShortName = wallet ? getChainShortCode(wallet.chain) : 'ETH';
  const isEthereum = isEthereumChain(chainShortName) || wallet?.chain === BLOCKCHAIN.BASE;

  // Bitcoin transactions are built and signed outside the app; the Wallets stack's TransferDetails screen
  // carries that manual flow (paste the signed hex), so a Bitcoin wallet leaves the EVM flow here.
  const handleSelectWallet = useCallback(
    (selected: Wallet) => {
      if (isBitcoinChain(getChainShortCode(selected.chain))) {
        navigation.navigate('Wallets', {
          screen: 'TransferDetails',
          initial: false,
          params: { wallet: selected },
        });
        return;
      }
      selectWallet(selected);
    },
    [navigation, selectWallet],
  );
  const canSubmit = !!toAddress && !!amount && !!selectedAsset && !isPreparing;

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

  const handleBack = useCallback(() => {
    if (step === 'enter-details') {
      reset();
    } else if (step === 'review') {
      reset();
      if (wallet) selectWallet(wallet);
    } else if (step === 'sign') {
      backToReview();
    }
  }, [step, reset, wallet, selectWallet, backToReview]);

  const handleDone = useCallback(() => {
    reset();
    onDone();
  }, [reset, onDone]);

  const renderContent = () => {
    if (step === 'select-wallet') {
      return <WalletSelectionStep wallets={wallets} isLoading={isLoading} onSelectWallet={handleSelectWallet} />;
    }

    if (!wallet) {
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
            <ActivityIndicator size="small" color={theme.colors.interactive.active} />
            <Text style={styles.placeholderTitle}>Broadcasting Transaction</Text>
            <Text style={styles.placeholderText}>Submitting your transaction to the network...</Text>
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
    if (step === 'broadcast' || step === 'success') return null;

    if (step === 'select-wallet') {
      return (
        <View style={styles.footer}>
          <SecondaryButton onPress={handleDone} size="medium">
            Cancel
          </SecondaryButton>
        </View>
      );
    }

    if (!wallet) return null;

    if (step === 'enter-details') {
      return (
        <View style={styles.footer}>
          <ButtonGroup
            secondaryButton={{
              label: 'Back',
              onPress: handleBack,
            }}
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
              isSoftwareWallet
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

      {!isSoftwareWallet && (
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
