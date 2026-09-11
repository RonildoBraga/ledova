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

const scannerTeardowns = new Map<string, Promise<void>>();

export function useQRScanner({
  scannerId,
  onScanSuccess,
  enabled = true,
  fps = 10,
  qrboxSize = 250,
}: UseQRScannerOptions): UseQRScannerReturn {
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRun = useRef<{ stop: () => void } | null>(null);
  const onScanSuccessRef = useRef(onScanSuccess);

  useEffect(() => {
    onScanSuccessRef.current = onScanSuccess;
  }, [onScanSuccess]);

  const stopScanner = useCallback(() => {
    activeRun.current?.stop();
  }, []);

  useEffect(() => {
    if (!enabled) {
      stopScanner();
      return;
    }

    setError(null);
    const previous = scannerTeardowns.get(scannerId) ?? Promise.resolve();
    let release!: () => void;
    let fail!: (reason: Error) => void;
    const stopped = new Promise<void>((resolve, reject) => {
      release = resolve;
      fail = reject;
    });
    const completed = Promise.all([previous, stopped]).then(() => {});
    scannerTeardowns.set(scannerId, completed);
    void completed.then(
      () => {
        if (scannerTeardowns.get(scannerId) === completed) scannerTeardowns.delete(scannerId);
      },
      () => {},
    );
    const run = {
      closed: false,
      processed: false,
      scanner: null as Html5Qrcode | null,
      starting: null as Promise<unknown> | null,
      stop: () => {
        if (run.closed) return;
        run.closed = true;
        clearTimeout(initTimer);
        if (activeRun.current === run) {
          activeRun.current = null;
          setIsScanning(false);
        }
        void (async () => {
          try {
            await run.starting?.catch(() => {});
            const state = run.scanner?.getState();
            if (state === 2 || state === 3) await run.scanner!.stop();
            release();
          } catch {
            fail(new Error('The previous camera could not be stopped. Reload before scanning again.'));
          }
        })();
      },
    };
    activeRun.current = run;
    const current = () => !run.closed && activeRun.current === run;

    const qrConfig = {
      fps,
      qrbox: { width: qrboxSize, height: qrboxSize },
    };

    const onSuccess = (decodedText: string) => {
      if (!current() || run.processed) return;
      run.processed = true;
      const callback = onScanSuccessRef.current;
      run.stop();
      callback(decodedText);
    };

    const initTimer = setTimeout(() => {
      void (async () => {
        try {
          if (!current()) return;
          if (!document.getElementById(scannerId)) throw new Error('Scanner element not found');
          const cameras = await Html5Qrcode.getCameras();
          if (!current()) return;
          if (!cameras?.length) throw new Error('No cameras found');
          await previous;
          if (!current()) return;
          if (!document.getElementById(scannerId)) throw new Error('Scanner element not found');
          const scanner = new Html5Qrcode(scannerId);
          run.scanner = scanner;
          run.starting = Promise.resolve().then(() => {
            if (current()) return scanner.start(cameras[0].id, qrConfig, onSuccess, () => {});
          });
          await run.starting;
          if (current()) setIsScanning(true);
        } catch (err) {
          if (!current()) return;
          setError(err instanceof Error ? err.message : 'Failed to start camera');
          run.stop();
        }
      })();
    }, 100);

    return run.stop;
  }, [enabled, scannerId, fps, qrboxSize, stopScanner]);

  return { isScanning, error, stopScanner };
}
