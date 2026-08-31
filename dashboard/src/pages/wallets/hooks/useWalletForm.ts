import { useState, useCallback, useRef, useEffect } from 'react';
import { URDecoder, UREncoder } from '@ngraveio/bc-ur';
import { Html5Qrcode } from 'html5-qrcode';
import { detectChainFromAddress, validateWalletAddress } from '@ledova/shared-utils';
import { getActiveChains, getChainByShortName, getChainConfig } from '@ledova/shared-constants';
import type { CreateWallet, DerivedAddress, HardwareWalletImport } from '@ledova/shared-types';

type FormStep = 'input' | 'selectAddresses';

interface UseWalletFormProps {
  userAccountUuid: string | undefined;
  onSubmit: (data: CreateWallet) => void;
  onBatchSubmit: (addresses: DerivedAddress[], importData: HardwareWalletImport) => void;
  preselectedChain?: 'BTC' | 'ETH' | null;
}

export function useWalletForm({ userAccountUuid, onSubmit, onBatchSubmit, preselectedChain }: UseWalletFormProps) {
  const [step, setStep] = useState<FormStep>('input');
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
  const [scanProgress, setScanProgress] = useState<{ received: number; total: number } | null>(null);
  const [scannerError, setScannerError] = useState<string | null>(null);

  // Scanner refs
  const html5QrCodeRef = useRef<Html5Qrcode | null>(null);
  const urDecoderRef = useRef<URDecoder | null>(null);
  const processedPartsRef = useRef<Set<string>>(new Set());

  const reset = useCallback(() => {
    setStep('input');
    setName('');
    setAddress('');
    setErrors({});
    setShowScanner(false);
    setScannedURString(null);
    setScanProgress(null);
    setScannerError(null);
    urDecoderRef.current = null;
    processedPartsRef.current.clear();
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

  // Handle QR scan result
  const handleQRScanResult = useCallback(
    (data: string) => {
      const dataLower = data.toLowerCase();
      const isBCUR = dataLower.startsWith('ur:');

      if (isBCUR) {
        // Hardware wallet animated QR code
        if (!urDecoderRef.current) {
          urDecoderRef.current = new URDecoder();
        }

        if (processedPartsRef.current.has(dataLower)) {
          return; // Already processed this part
        }

        processedPartsRef.current.add(dataLower);

        try {
          urDecoderRef.current.receivePart(dataLower);

          const estimatedPercentComplete = urDecoderRef.current.estimatedPercentComplete();
          const receivedParts = processedPartsRef.current.size;
          setScanProgress({
            received: receivedParts,
            total: estimatedPercentComplete > 0 ? Math.ceil(receivedParts / estimatedPercentComplete) : receivedParts,
          });

          if (urDecoderRef.current.isComplete()) {
            const ur = urDecoderRef.current.resultUR();
            // Use a large fragment size to ensure the entire UR fits in one part
            const encoder = new UREncoder(ur, 100000);
            const completeURString = encoder.nextPart();

            // Stop scanner
            stopScanner();
            setScannedURString(completeURString);
            setShowScanner(false);
            setStep('selectAddresses');
          }
        } catch {
          // Continue scanning, ignore errors
        }
        return;
      }

      // Plain address - stop scanner and use the address
      stopScanner();
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

  // Stop QR scanner
  const stopScanner = useCallback(() => {
    if (html5QrCodeRef.current) {
      html5QrCodeRef.current.stop().catch(() => {});
      html5QrCodeRef.current = null;
    }
    urDecoderRef.current = null;
    processedPartsRef.current.clear();
    setScanProgress(null);
    setScannerError(null);
  }, []);

  // Initialize QR scanner
  const startScanner = useCallback(() => {
    if (html5QrCodeRef.current) return;

    const html5QrCode = new Html5Qrcode('wallet-qr-scanner');
    html5QrCodeRef.current = html5QrCode;

    const qrConfig = {
      fps: 10,
      qrbox: { width: 250, height: 250 },
    };

    Html5Qrcode.getCameras()
      .then((cameras) => {
        if (cameras && cameras.length > 0) {
          const cameraId = cameras[0].id;
          return html5QrCode.start(cameraId, qrConfig, handleQRScanResult, () => {});
        } else {
          throw new Error('No cameras found');
        }
      })
      .catch((err) => {
        console.error('Failed to start QR scanner:', err);
        setScannerError('Unable to access camera. Please check permissions.');
      });
  }, [handleQRScanResult]);

  // Effect to start/stop scanner when showScanner changes
  useEffect(() => {
    if (showScanner) {
      // Small delay to ensure DOM element exists
      const timer = setTimeout(startScanner, 100);
      return () => clearTimeout(timer);
    } else {
      stopScanner();
    }
  }, [showScanner, startScanner, stopScanner]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopScanner();
    };
  }, [stopScanner]);

  const handleAddressSelection = useCallback(
    (addresses: DerivedAddress[], importData: HardwareWalletImport) => {
      onBatchSubmit(addresses, importData);
    },
    [onBatchSubmit],
  );

  const handleBackToInput = useCallback(() => {
    setStep('input');
    setScannedURString(null);
    setScanProgress(null);
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
    });
  }, [validate, selectedChain, userAccountUuid, name, address, onSubmit]);

  const toggleScanner = useCallback(() => {
    setShowScanner((prev) => !prev);
    setScannerError(null);
    setScanProgress(null);
    urDecoderRef.current = null;
    processedPartsRef.current.clear();
  }, []);

  return {
    // State
    step,
    name,
    address,
    selectedChain,
    errors,
    showScanner,
    scannedURString,
    scanProgress,
    scannerError,
    isSelectingAddresses: step === 'selectAddresses' && !!scannedURString,

    // Setters
    setName,

    // Actions
    reset,
    handleAddressChange,
    handleAddressSelection,
    handleBackToInput,
    handleSubmit,
    toggleScanner,
    stopScanner,
  };
}
