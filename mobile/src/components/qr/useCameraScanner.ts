import { useCallback, useContext, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { AppState, Platform } from 'react-native';
import { Camera } from 'expo-camera';
import type { PermissionResponse } from 'expo-camera';
import { CameraAccessContext } from '../../contexts/cameraAccess';
import { createCameraWindowAccess } from './cameraWindowAccess';

type CameraStatus = 'inactive' | 'loading' | 'denied' | 'failed' | 'ready' | 'scanned';
type BarcodeHandler = (result: { data: string }) => void;
type CameraSnapshot = { status: CameraStatus; previewKey?: string; onBarcodeScanned?: BarcodeHandler };

const messages = {
  inactive: 'Camera paused.',
  loading: 'Requesting camera permission...',
  denied: 'Camera permission is required to scan QR codes. Please enable it in settings.',
  failed: 'Camera permission is unavailable. Close the scanner and try again.',
  scanned: '✓ Scanned!',
};

let pendingRequest: Promise<PermissionResponse> | null = null;
let latestRequest: Promise<PermissionResponse> | null = null;

async function readPermission(allowRequest: boolean, isCurrent: () => boolean): Promise<PermissionResponse> {
  if (pendingRequest) {
    const response = await pendingRequest;
    if (allowRequest || !isCurrent()) return response;
  }

  const previousRequest = latestRequest;
  const response = await Camera.getCameraPermissionsAsync();
  if (!isCurrent() || !allowRequest || response.granted || !response.canAskAgain) return response;
  if (latestRequest && latestRequest !== previousRequest) return latestRequest;
  if (!pendingRequest) {
    pendingRequest = Camera.requestCameraPermissionsAsync().finally(() => {
      pendingRequest = null;
    });
    latestRequest = pendingRequest;
  }
  return pendingRequest;
}

export function useCameraScanner(
  enabled: boolean,
  onScan: (data: string, finishScan: () => void) => void,
  sessionKey = '',
) {
  const cameraAccess = useContext(CameraAccessContext);
  const windowAccess = useMemo(() => createCameraWindowAccess(Platform.OS === 'android', sessionKey), [sessionKey]);
  const [snapshot, setSnapshot] = useState<CameraSnapshot>({ status: 'inactive' });
  const onScanRef = useRef(onScan);
  const stopRef = useRef(() => {});

  useLayoutEffect(() => {
    onScanRef.current = onScan;
  }, [onScan]);

  useLayoutEffect(() => {
    if (!enabled) {
      setSnapshot({ status: 'inactive' });
      return;
    }

    let stopped = false;
    let foreground = AppState.currentState === 'active';
    let revision = 0;
    let completed = false;
    let processing = false;
    let initialRequest = foreground && cameraAccess.getSnapshot().allowed;
    let windowAdmitted = windowAccess.getSnapshot().allowed;

    const refresh = async (allowRequest: boolean) => {
      const currentRevision = ++revision;
      const access = cameraAccess.getSnapshot();
      const window = windowAccess.getSnapshot();
      const isCurrent = () =>
        !stopped &&
        foreground &&
        revision === currentRevision &&
        access.allowed &&
        window.allowed &&
        windowAccess.getSnapshot() === window &&
        cameraAccess.getSnapshot() === access;
      if (!isCurrent()) {
        if (!stopped) setSnapshot({ status: 'inactive' });
        return;
      }
      if (completed) {
        setSnapshot({ status: 'scanned' });
        return;
      }
      setSnapshot({ status: 'loading' });
      initialRequest = false;
      try {
        const permission = await readPermission(allowRequest, isCurrent);
        if (!isCurrent()) return;
        if (!permission.granted) {
          setSnapshot({ status: 'denied' });
          return;
        }
        setSnapshot({
          status: 'ready',
          previewKey: window.key,
          onBarcodeScanned: ({ data }) => {
            if (!isCurrent() || completed || processing) return;
            processing = true;
            try {
              onScanRef.current(data, () => {
                completed = true;
                if (isCurrent()) setSnapshot({ status: 'scanned' });
              });
            } finally {
              processing = false;
            }
          },
        });
      } catch {
        if (isCurrent()) setSnapshot({ status: 'failed' });
      }
    };

    stopRef.current = () => {
      stopped = true;
      revision += 1;
      setSnapshot({ status: 'inactive' });
    };

    const unsubscribeWindow = windowAccess.subscribe(() => {
      if (stopped) return;
      const admitted = windowAccess.getSnapshot().allowed;
      if (!admitted) {
        if (windowAdmitted) initialRequest = false;
        revision += 1;
        setSnapshot({ status: 'inactive' });
      } else {
        void refresh(initialRequest);
      }
      windowAdmitted = admitted;
    });

    const unsubscribeAccess = cameraAccess.subscribe(() => {
      if (stopped) return;
      if (foreground && cameraAccess.getSnapshot().allowed) void refresh(false);
      else {
        initialRequest = false;
        revision += 1;
        setSnapshot({ status: 'inactive' });
      }
    });

    const subscription = AppState.addEventListener('change', (state) => {
      if (stopped) return;
      const nextForeground = state === 'active';
      if (foreground === nextForeground) return;
      foreground = nextForeground;
      if (foreground) {
        void refresh(false);
      } else {
        initialRequest = false;
        revision += 1;
        setSnapshot({ status: 'inactive' });
      }
    });

    if (foreground) void refresh(true);
    else setSnapshot({ status: 'inactive' });

    return () => {
      stopped = true;
      revision += 1;
      stopRef.current = () => {};
      subscription.remove();
      unsubscribeAccess();
      unsubscribeWindow();
    };
  }, [cameraAccess, enabled, sessionKey, windowAccess]);

  const stop = useCallback(() => stopRef.current(), []);
  const status = enabled ? snapshot.status : 'inactive';
  return { ...snapshot, windowAccess, status, message: status === 'ready' ? null : messages[status], stop };
}
