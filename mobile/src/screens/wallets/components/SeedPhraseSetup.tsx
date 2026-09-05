import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { Text } from 'react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import {
  generateMnemonic,
  validateMnemonic,
  computeSeedIdentifier,
  storeSeedPhrase,
} from '../../../services/secureKeyStorage';
import { deriveAccountsFromMnemonic } from '../../../utils/softwareWallet';
import type { DerivedAddress } from '@ledova/shared';
import type { SoftwareWalletImport } from '../../../utils/softwareWallet';
import { useFetchBalances } from '../../../hooks';
import * as LocalAuthentication from 'expo-local-authentication';
import { CustomModal } from '../../../components/modal';
import { SeedPhraseGenerate } from './SeedPhraseGenerate';
import { SeedPhraseConfirm } from './SeedPhraseConfirm';
import { SeedAccountSelector } from './SeedAccountSelector';

const SEED_STEP = {
  GENERATE: 'generate',
  CONFIRM: 'confirm',
  SELECT_ACCOUNTS: 'selectAccounts',
  STORING: 'storing',
} as const;

type SeedStep = (typeof SEED_STEP)[keyof typeof SEED_STEP];
type InputMode = 'create' | 'import';

interface SeedPhraseSetupProps {
  visible: boolean;
  onClose: () => void;
  onComplete: (addresses: DerivedAddress[], importData: SoftwareWalletImport) => void;
  onCancel: () => void;
}

export function SeedPhraseSetup({ visible, onClose, onComplete, onCancel }: SeedPhraseSetupProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    storingContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.md,
    },
    storingText: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.muted,
    },
  }));
  const [step, setStep] = useState<SeedStep>(SEED_STEP.GENERATE);
  const [inputMode, setInputMode] = useState<InputMode>('create');
  const [mnemonic, setMnemonic] = useState<string>('');
  const [importWords, setImportWords] = useState<string[]>(Array(12).fill(''));
  const [importError, setImportError] = useState<string | null>(null);

  const [quizPositions, setQuizPositions] = useState<number[]>([]);
  const [quizAnswers, setQuizAnswers] = useState<string[]>(['', '', '']);
  const [quizError, setQuizError] = useState<string | null>(null);

  const [derivedData, setDerivedData] = useState<SoftwareWalletImport | null>(null);
  const [selectedAddresses, setSelectedAddresses] = useState<Set<string>>(new Set());
  const { balances, fetchBalances } = useFetchBalances();

  const [storeError, setStoreError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) {
      setMnemonic('');
      setImportWords(Array(12).fill(''));
      setDerivedData(null);
      setSelectedAddresses(new Set());
      setQuizPositions([]);
      setQuizAnswers(['', '', '']);
      setQuizError(null);
      setImportError(null);
      setStoreError(null);
      setStep(SEED_STEP.GENERATE);
    }
  }, [visible]);

  useEffect(() => {
    if (inputMode === 'create' && !mnemonic && visible) {
      setMnemonic(generateMnemonic());
    }
  }, [inputMode, mnemonic, visible]);

  useEffect(() => {
    if (step === SEED_STEP.CONFIRM && mnemonic) {
      const positions: number[] = [];
      while (positions.length < 3) {
        const pos = Math.floor(Math.random() * 12);
        if (!positions.includes(pos)) positions.push(pos);
      }
      positions.sort((a, b) => a - b);
      setQuizPositions(positions);
      setQuizAnswers(['', '', '']);
      setQuizError(null);
    }
  }, [step, mnemonic]);

  const words = useMemo(() => mnemonic.split(' '), [mnemonic]);

  const handleImportWordChange = useCallback((index: number, value: string) => {
    setImportWords((prev) => {
      const updated = [...prev];
      updated[index] = value.toLowerCase().trim();
      return updated;
    });
    setImportError(null);
  }, []);

  const deriveAndShowAccounts = useCallback(
    (mnemonicPhrase: string) => {
      const data = deriveAccountsFromMnemonic(mnemonicPhrase);
      setDerivedData(data);
      setSelectedAddresses(new Set(data.addresses.map((a) => a.address)));
      setStep(SEED_STEP.SELECT_ACCOUNTS);
      fetchBalances(data.addresses);
    },
    [fetchBalances],
  );

  const handleProceedFromGenerate = useCallback(() => {
    if (inputMode === 'import') {
      const joined = importWords.join(' ');
      if (!validateMnemonic(joined)) {
        setImportError('Invalid recovery phrase. Please check all 12 words.');
        return;
      }
      setMnemonic(joined);
      deriveAndShowAccounts(joined);
    } else {
      setStep(SEED_STEP.CONFIRM);
    }
  }, [inputMode, importWords, deriveAndShowAccounts]);

  const handleConfirmQuiz = useCallback(() => {
    const mnemonicWords = mnemonic.split(' ');
    for (let i = 0; i < quizPositions.length; i++) {
      if (quizAnswers[i].toLowerCase().trim() !== mnemonicWords[quizPositions[i]]) {
        setQuizError('One or more answers are incorrect. Please try again.');
        return;
      }
    }
    deriveAndShowAccounts(mnemonic);
  }, [mnemonic, quizPositions, quizAnswers, deriveAndShowAccounts]);

  const handleQuizAnswerChange = useCallback((index: number, text: string) => {
    setQuizAnswers((prev) => {
      const updated = [...prev];
      updated[index] = text;
      return updated;
    });
    setQuizError(null);
  }, []);

  const toggleAddressSelection = useCallback((address: string) => {
    setSelectedAddresses((prev) => {
      const next = new Set(prev);
      if (next.has(address)) next.delete(address);
      else next.add(address);
      return next;
    });
  }, []);

  const handleStoreAndCreate = useCallback(async () => {
    if (!derivedData || selectedAddresses.size === 0) return;

    setStep(SEED_STEP.STORING);
    setStoreError(null);

    try {
      const authResult = await LocalAuthentication.authenticateAsync({
        promptMessage: 'Authenticate to store your recovery phrase',
        fallbackLabel: 'Use passcode',
        disableDeviceFallback: false,
      });

      if (!authResult.success) {
        setStep(SEED_STEP.SELECT_ACCOUNTS);
        return;
      }

      const seedId = computeSeedIdentifier(mnemonic);
      await storeSeedPhrase(seedId, mnemonic);

      const selected = derivedData.addresses.filter((a) => selectedAddresses.has(a.address));
      onComplete(selected, derivedData);
    } catch (err) {
      setStoreError(err instanceof Error ? err.message : 'Failed to store recovery phrase');
      setStep(SEED_STEP.SELECT_ACCOUNTS);
    }
  }, [derivedData, selectedAddresses, mnemonic, onComplete]);

  const getFooterProps = () => {
    switch (step) {
      case SEED_STEP.GENERATE:
        return {
          cancelLabel: 'Back' as const,
          onCancel: onCancel,
          confirmLabel: inputMode === 'create' ? 'Continue' : 'Import',
          onConfirm: handleProceedFromGenerate,
        };
      case SEED_STEP.CONFIRM:
        return {
          cancelLabel: 'Back' as const,
          onCancel: () => setStep(SEED_STEP.GENERATE),
          confirmLabel: 'Verify',
          onConfirm: handleConfirmQuiz,
          confirmDisabled: quizAnswers.some((a) => !a),
        };
      default:
        return {
          cancelLabel: 'Back' as const,
          onCancel: onCancel,
        };
    }
  };

  const renderContent = () => {
    switch (step) {
      case SEED_STEP.GENERATE:
        return (
          <SeedPhraseGenerate
            inputMode={inputMode}
            words={words}
            importWords={importWords}
            importError={importError}
            onInputModeChange={setInputMode}
            onImportWordChange={handleImportWordChange}
          />
        );

      case SEED_STEP.CONFIRM:
        return (
          <SeedPhraseConfirm
            quizPositions={quizPositions}
            quizAnswers={quizAnswers}
            quizError={quizError}
            onAnswerChange={handleQuizAnswerChange}
          />
        );

      case SEED_STEP.SELECT_ACCOUNTS:
        if (!derivedData) return null;
        return (
          <SeedAccountSelector
            addresses={derivedData.addresses}
            selectedAddresses={selectedAddresses}
            balances={balances}
            storeError={storeError}
            onToggleAddress={toggleAddressSelection}
            onConfirm={handleStoreAndCreate}
            onBack={() => setStep(inputMode === 'import' ? SEED_STEP.GENERATE : SEED_STEP.CONFIRM)}
          />
        );

      case SEED_STEP.STORING:
        return (
          <View style={styles.storingContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
            <Text style={styles.storingText}>Securing your wallet...</Text>
          </View>
        );

      default:
        return null;
    }
  };

  return (
    <CustomModal visible={visible} onClose={onClose} showFooter={true} {...getFooterProps()}>
      {renderContent()}
    </CustomModal>
  );
}
