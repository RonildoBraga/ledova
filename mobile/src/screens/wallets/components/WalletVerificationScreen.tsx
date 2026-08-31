import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { View, ScrollView } from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { useCameraPermissions } from 'expo-camera';
import { GradientBackground } from '../../../components/GradientBackground';
import { Panel } from '../../../components/panel';
import { encodeEthereumMessage, encodeBitcoinMessage } from '../../../utils/keystone/urEncoder';
import { decodeKeystoneMessageSignature } from '../../../utils/keystone/urDecoder';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import {
  getChainShortCode,
  BLOCKCHAIN,
  isBitcoinChain,
  getWalletVerificationEvmChainId,
  WALLET_TYPE,
} from '@ledova/shared-constants';
import type { WalletsStackParamList } from '../../../navigation/WalletsStackNavigator';
import { ButtonGroup } from '../../../components/buttons';
import { useWalletVerification } from '../useWalletVerification';
import { VerificationInstructions } from './VerificationInstructions';
import { ChallengeQRStep } from './ChallengeQRStep';
import { SignatureScanStep } from './SignatureScanStep';

type WalletVerificationRouteProp = RouteProp<WalletsStackParamList, 'WalletVerification'>;

export function WalletVerificationScreen() {
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
    scrollView: {
      flex: 1,
    },
    scrollViewContent: {
      padding: theme.spacing.xs,
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
  const navigation = useNavigation();
  const route = useRoute<WalletVerificationRouteProp>();
  const [permission, requestPermission] = useCameraPermissions();
  const [hasScanned, setHasScanned] = useState(false);
  const scanLockRef = useRef(false);

  const { wallet } = route.params;

  const isSoftwareWallet = wallet.walletType === WALLET_TYPE.SOFTWARE;

  const {
    verificationChallenge,
    verificationStep,
    isRequestingChallenge,
    isVerifying,
    verificationError,
    verificationSuccess,
    requestChallenge,
    proceedToScanSignature,
    goBackVerificationStep,
    verifySignature,
    autoVerify,
    reset,
  } = useWalletVerification({ wallet });

  const hasAutoVerified = useRef(false);
  useEffect(() => {
    if (isSoftwareWallet && !hasAutoVerified.current) {
      hasAutoVerified.current = true;
      autoVerify();
    }
  }, [isSoftwareWallet]);

  useEffect(() => {
    if (verificationStep === 'scan-signature' && !permission) {
      requestPermission();
    }
    if (verificationStep === 'scan-signature') {
      setHasScanned(false);
      scanLockRef.current = false;
    }
  }, [verificationStep, permission, requestPermission]);

  useEffect(() => {
    return () => {
      reset();
    };
  }, [reset]);

  useEffect(() => {
    if (verificationSuccess) {
      const timer = setTimeout(() => {
        navigation.goBack();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [verificationSuccess, navigation]);

  const chainShortName = getChainShortCode(wallet?.chain || BLOCKCHAIN.ETHEREUM);
  const isBitcoin = isBitcoinChain(chainShortName);
  const evmChainId = wallet ? getWalletVerificationEvmChainId(wallet.chain) : null;

  const urEncodedChallenge = useMemo(() => {
    if (!verificationChallenge || !wallet) return null;
    if (!wallet.derivationPath || !wallet.masterFingerprint) return null;

    try {
      let encoded: { type: string; cbor: Buffer; urString: string } | null = null;

      if (evmChainId !== null) {
        encoded = encodeEthereumMessage(
          wallet.address,
          verificationChallenge,
          wallet.derivationPath,
          wallet.masterFingerprint,
          evmChainId,
        );
      } else if (isBitcoin) {
        encoded = encodeBitcoinMessage(
          wallet.address,
          verificationChallenge,
          wallet.derivationPath,
          wallet.masterFingerprint,
        );
      } else {
        return null;
      }

      return encoded?.urString || null;
    } catch {
      return null;
    }
  }, [verificationChallenge, wallet, evmChainId, isBitcoin]);

  const handleSignatureScanned = useCallback(
    ({ data }: { data: string }) => {
      if (scanLockRef.current) return;
      scanLockRef.current = true;
      setHasScanned(true);

      const decodedSignature = decodeKeystoneMessageSignature(data);
      if (decodedSignature) {
        verifySignature(decodedSignature);
      }
    },
    [verifySignature],
  );

  const renderFooter = () => {
    if (verificationStep === 'instructions') {
      if (isSoftwareWallet) {
        return (
          <View style={styles.footer}>
            <ButtonGroup
              primaryButton={{
                label: verificationError ? 'Retry' : 'Cancel',
                onPress: verificationError ? autoVerify : () => navigation.goBack(),
                disabled: isRequestingChallenge || isVerifying,
                loading: isRequestingChallenge || isVerifying,
              }}
              size="medium"
            />
          </View>
        );
      }

      return (
        <View style={styles.footer}>
          <ButtonGroup
            primaryButton={{
              label: 'Start',
              onPress: requestChallenge,
              disabled: isRequestingChallenge,
              loading: isRequestingChallenge,
            }}
            size="medium"
          />
        </View>
      );
    }

    if (verificationStep === 'show-challenge-qr') {
      return (
        <View style={styles.footer}>
          <ButtonGroup
            primaryButton={{
              label: 'Continue',
              onPress: proceedToScanSignature,
            }}
            size="medium"
          />
        </View>
      );
    }

    if (verificationStep === 'scan-signature') {
      return (
        <View style={styles.footer}>
          <ButtonGroup
            primaryButton={{
              label: 'Back',
              onPress: goBackVerificationStep,
            }}
            size="medium"
          />
        </View>
      );
    }

    return null;
  };

  if (!wallet) {
    navigation.goBack();
    return null;
  }

  return (
    <GradientBackground>
      <View style={styles.container}>
        <View style={styles.content}>
          <Panel fullHeight>
            <View style={styles.panelContent}>
              <ScrollView
                style={styles.scrollView}
                contentContainerStyle={styles.scrollViewContent}
                showsVerticalScrollIndicator={false}
              >
                {verificationStep === 'instructions' && (
                  <VerificationInstructions
                    isSoftwareWallet={isSoftwareWallet}
                    isRequestingChallenge={isRequestingChallenge}
                    isVerifying={isVerifying}
                    verificationSuccess={verificationSuccess}
                    verificationError={verificationError}
                  />
                )}
                {verificationStep === 'show-challenge-qr' && (
                  <ChallengeQRStep urEncodedChallenge={urEncodedChallenge} />
                )}
                {verificationStep === 'scan-signature' && (
                  <SignatureScanStep
                    permission={permission ?? null}
                    hasScanned={hasScanned}
                    isVerifying={isVerifying}
                    verificationSuccess={verificationSuccess}
                    verificationError={verificationError}
                    onBarcodeScanned={handleSignatureScanned}
                  />
                )}
              </ScrollView>

              {renderFooter()}
            </View>
          </Panel>
        </View>
      </View>
    </GradientBackground>
  );
}
