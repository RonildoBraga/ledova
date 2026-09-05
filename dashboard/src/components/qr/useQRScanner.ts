import { useState, useEffect, useRef, useCallback } from 'react';
import { Html5Qrcode } from 'html5-qrcode';

interface UseQRScannerOptions {
  scannerId: string;
  onScanSuccess: (decodedText: string) => void;
  enabled?: boolean;
  fps?: number;
  qrboxSize?: number;
}

interface UseQRScannerReturn {
  isScanning: boolean;
  error: string | null;
  stopScanner: () => void;
}

export function useQRScanner({
  scannerId,
  onScanSuccess,
  enabled = true,
  fps = 10,
  qrboxSize = 250,
}: UseQRScannerOptions): UseQRScannerReturn {
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const html5QrCodeRef = useRef<Html5Qrcode | null>(null);
  const hasProcessedRef = useRef(false);
  const onScanSuccessRef = useRef(onScanSuccess);

  useEffect(() => {
    onScanSuccessRef.current = onScanSuccess;
  }, [onScanSuccess]);

  const stopScanner = useCallback(() => {
    const scanner = html5QrCodeRef.current;
    if (scanner) {
      try {
        const state = scanner.getState();
        if (state === 2 || state === 3) {
          scanner.stop().catch(() => {});
        }
      } catch {}
      html5QrCodeRef.current = null;
    }
    setIsScanning(false);
  }, []);

  useEffect(() => {
    if (!enabled) {
      stopScanner();
      return;
    }

    hasProcessedRef.current = false;
    setError(null);

    const qrConfig = {
      fps,
      qrbox: { width: qrboxSize, height: qrboxSize },
    };

    const onSuccess = (decodedText: string) => {
      if (hasProcessedRef.current) return;
      hasProcessedRef.current = true;
      stopScanner();
      onScanSuccessRef.current(decodedText);
    };

    const initTimer = setTimeout(() => {
      const scannerElement = document.getElementById(scannerId);
      if (!scannerElement) {
        setError('Scanner element not found');
        return;
      }

      const html5QrCode = new Html5Qrcode(scannerId);
      html5QrCodeRef.current = html5QrCode;

      Html5Qrcode.getCameras()
        .then((cameras) => {
          if (cameras && cameras.length > 0) {
            return html5QrCode.start(cameras[0].id, qrConfig, onSuccess, () => {});
          }
          throw new Error('No cameras found');
        })
        .then(() => {
          setIsScanning(true);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : 'Failed to start camera');
        });
    }, 100);

    return () => {
      clearTimeout(initTimer);
      stopScanner();
    };
  }, [enabled, scannerId, fps, qrboxSize, stopScanner]);

  return { isScanning, error, stopScanner };
}
