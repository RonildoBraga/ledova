import { useState, useCallback } from 'react';
import { getActiveChains, getChainByShortName, getChainConfig } from '@ledova/shared-constants';
import { validateWalletAddress, detectChainFromAddress } from '@ledova/shared-utils';
import type { DerivedAddress, HardwareWalletImport, CreateWallet, WalletType } from '@ledova/shared-types';

export const FORM_STEPS = {
  SELECT_TYPE: 'selectType',
  INPUT: 'input',
  SELECT_ADDRESSES: 'selectAddresses',
  SEED_PHRASE: 'seedPhrase',
} as const;

type FormStep = (typeof FORM_STEPS)[keyof typeof FORM_STEPS];

interface UseAddWalletFormProps {
  userAccountUuid: string | undefined;
  onSubmit: (data: CreateWallet) => void;
  onBatchSubmit: (addresses: DerivedAddress[], importData: HardwareWalletImport) => void;
  preselectedChain?: 'BTC' | 'ETH' | null;
}

export function useAddWalletForm({
  userAccountUuid,
  onSubmit,
  onBatchSubmit,
  preselectedChain,
}: UseAddWalletFormProps) {
  const [step, setStep] = useState<FormStep>(FORM_STEPS.SELECT_TYPE);
  const [walletType, setWalletType] = useState<WalletType | null>(null);
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [selectedChain, setSelectedChain] = useState<string | null>(() => {
    if (preselectedChain) {
      const chain = getChainByShortName(preselectedChain);
      return chain?.code || null;
    }
    const activeChains = getActiveChains();
    return activeChains[0]?.code || null;
  });
  const [errors, setErrors] = useState<{ address?: string; network?: string }>({});
  const [showScanner, setShowScanner] = useState(false);
  const [scannedURString, setScannedURString] = useState<string | null>(null);

  const reset = useCallback(() => {
    setStep(FORM_STEPS.SELECT_TYPE);
    setWalletType(null);
    setName('');
    setAddress('');
    setErrors({});
    setShowScanner(false);
    setScannedURString(null);
    const activeChains = getActiveChains();
    setSelectedChain(activeChains[0]?.code || null);
  }, []);

  const validate = useCallback((): boolean => {
    const newErrors: { address?: string; network?: string } = {};

    if (!address.trim()) {
      newErrors.address = 'Wallet address is required';
    } else {
      let networkToValidate = selectedChain;

      if (!networkToValidate) {
        const detectedShortName = detectChainFromAddress(address);
        if (detectedShortName) {
          const detectedChain = getChainByShortName(detectedShortName);
          if (detectedChain) {
            networkToValidate = detectedChain.code;
            setSelectedChain(networkToValidate);
          }
        }
      }

      if (!networkToValidate) {
        newErrors.address = 'Could not detect network from address. Please check the address format.';
      } else {
        const chain = getChainConfig(networkToValidate);
        if (chain && !validateWalletAddress(address, chain.shortName)) {
          newErrors.address = `Invalid ${chain.name} address format`;
        }
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [address, selectedChain]);

  const handleAddressChange = useCallback(
    (text: string) => {
      setAddress(text);

      if (text.length > 10) {
        const detectedShortName = detectChainFromAddress(text);
        if (detectedShortName) {
          const chain = getChainByShortName(detectedShortName);
          if (chain && chain.code !== selectedChain) {
            setSelectedChain(chain.code);
          }
        }
      }

      if (errors.address) {
        setErrors((prev) => ({ ...prev, address: undefined }));
      }
    },
    [selectedChain, errors.address],
  );

  const handleQRScan = useCallback(
    (data: string) => {
      const dataLower = data.toLowerCase();
      const isBCUR = dataLower.startsWith('ur:');

      if (isBCUR) {
        setScannedURString(data);
        setShowScanner(false);
        setStep(FORM_STEPS.SELECT_ADDRESSES);
        return;
      }

      setAddress(data);
      setShowScanner(false);

      const detectedShortName = detectChainFromAddress(data);
      if (detectedShortName) {
        const chain = getChainByShortName(detectedShortName);
        if (chain) {
          setSelectedChain(chain.code);
        }
      }

      if (errors.address) {
        setErrors((prev) => ({ ...prev, address: undefined }));
      }
    },
    [errors.address],
  );

  const handleAddressSelection = useCallback(
    (addresses: DerivedAddress[], importData: HardwareWalletImport) => {
      // Pass the selected addresses and import data to the parent
      onBatchSubmit(addresses, importData);
    },
    [onBatchSubmit],
  );

  const handleBackToInput = useCallback(() => {
    setStep(FORM_STEPS.INPUT);
    setScannedURString(null);
  }, []);

  const handleSubmit = useCallback(() => {
    if (!validate() || !selectedChain || !userAccountUuid) {
      return;
    }

    onSubmit({
      userAccount: userAccountUuid,
      name: name.trim() || undefined,
      address: address.trim(),
      chain: selectedChain,
      walletType: walletType || 'hardware',
    });
  }, [validate, selectedChain, userAccountUuid, name, address, walletType, onSubmit]);

  const toggleScanner = useCallback(() => {
    setShowScanner((prev) => !prev);
  }, []);

  const setShowScannerDirect = useCallback((value: boolean) => {
    setShowScanner(value);
  }, []);

  return {
    // State
    step,
    walletType,
    name,
    address,
    selectedChain,
    errors,
    showScanner,
    scannedURString,
    isSelectingAddresses: step === FORM_STEPS.SELECT_ADDRESSES && !!scannedURString,

    // Setters
    setName,
    setStep,
    setWalletType,
    setShowScannerDirect,

    // Actions
    reset,
    handleAddressChange,
    handleQRScan,
    handleAddressSelection,
    handleBackToInput,
    handleSubmit,
    toggleScanner,
  };
}
