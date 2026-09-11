import { useCallback, useEffect, useRef, useState, type Ref } from 'react';
import { Button, Modal, View, Text, Platform, type ViewProps } from 'react-native';
import { requireNativeView } from 'expo';
import { CameraAccessContext, createCameraAccess } from '../src/contexts/cameraAccess';
import { ScannerPreview } from '../src/components/qr/ScannerPreview';
import { useCameraScanner } from '../src/components/qr/useCameraScanner';
import { failureCategory } from './diagnostics';

type Props = { onComplete: (passed: boolean, stage?: string) => void };
type NativeHandle = { isCurrentScan: (generation: number, scanId: number) => Promise<boolean> };
const InactiveProbe =
  Platform.OS === 'android'
    ? requireNativeView<
        ViewProps & {
          active: boolean;
          generation: number;
          scanId: number;
          ref: Ref<NativeHandle>;
        }
      >('LedovaScanner')
    : null;

function WindowProbe({ onComplete, onActiveUnmount }: Props & { onActiveUnmount?: () => void }) {
  const [scans, setScans] = useState(0);
  const camera = useCameraScanner(true, (_data, finish) => {
    setScans((count) => count + 1);
    finish();
  });
  const [stage, setStage] = useState<'opening' | 'covered' | 'returning'>('opening');
  const [firstGeneration, setFirstGeneration] = useState(-1);
  const [methodReady, setMethodReady] = useState(false);
  const native = useRef<NativeHandle | null>(null);
  const queryStarted = useRef(false);
  const checkNativeMethod = () => {
    if (queryStarted.current) return;
    queryStarted.current = true;
    if (!native.current) {
      onComplete(false, 'missing-ref');
      return;
    }
    if (typeof native.current.isCurrentScan !== 'function') {
      onComplete(false, 'missing-method');
      return;
    }
    native.current
      .isCurrentScan(-1, 0)
      .then((allowed) => (allowed ? onComplete(false, 'inactive-admitted') : setMethodReady(true)))
      .catch((error) => onComplete(false, `method-${failureCategory(error)}`));
  };
  useEffect(() => {
    const deadline = setTimeout(() => onComplete(false, 'window-timeout'), 60000);
    return () => clearTimeout(deadline);
  }, [onComplete]);

  return (
    <Modal visible animationType="none">
      <View style={{ width: 240, height: 240 }}>
        <ScannerPreview {...camera.preview} />
        <Text>{camera.status}</Text>
      </View>
      <Text accessibilityLabel="scanner-probe-state">
        {`${camera.status}|${camera.preview.generation}|${camera.preview.scanId}|${scans}`}
      </Text>
      {onActiveUnmount && camera.status === 'ready' && methodReady && (
        <Button
          title="Unmount active scanner"
          accessibilityLabel="scanner-probe-unmount-active"
          onPress={onActiveUnmount}
        />
      )}
      {!onActiveUnmount &&
        stage !== 'covered' &&
        (camera.status === 'ready' || camera.status === 'scanned') &&
        methodReady && (
          <Button
            title="Cover scanner"
            accessibilityLabel="scanner-probe-cover"
            onPress={() => {
              if (stage === 'opening') setFirstGeneration(camera.preview.window.getSnapshot().generation);
              setStage('covered');
            }}
          />
        )}
      {stage === 'returning' && camera.status === 'scanned' && (
        <Button
          title="Complete scanner check"
          accessibilityLabel="scanner-probe-complete"
          onPress={() => onComplete(scans === 1 && camera.preview.window.getSnapshot().generation > firstGeneration)}
        />
      )}
      {InactiveProbe && (
        <InactiveProbe
          ref={native}
          active={false}
          generation={-1}
          scanId={0}
          onLayout={checkNativeMethod}
          style={{ width: 1, height: 1 }}
        />
      )}
      <Modal visible={stage === 'covered'} transparent animationType="none">
        <View style={{ paddingTop: 64 }}>
          <Text>Synthetic scanner window cover</Text>
          <Button
            title="Return to scanner"
            accessibilityLabel="scanner-probe-return"
            onPress={() => setStage('returning')}
          />
        </View>
      </Modal>
    </Modal>
  );
}

export function ScannerBridgeProbe({ onComplete }: Props) {
  const [stage, setStage] = useState<'active' | 'unmounted' | 'continuation' | 'completed'>('active');
  const [access] = useState(() => {
    const value = createCameraAccess();
    value.setAllowed(true);
    return value;
  });
  const completeWindow = useCallback(
    (passed: boolean, failureStage?: string) => {
      if (passed) setStage('completed');
      else onComplete(false, failureStage);
    },
    [onComplete],
  );
  return (
    <CameraAccessContext.Provider value={access}>
      {(stage === 'active' || stage === 'continuation') && (
        <WindowProbe
          key={stage}
          onComplete={completeWindow}
          onActiveUnmount={stage === 'active' ? () => setStage('unmounted') : undefined}
        />
      )}
      {stage === 'unmounted' && (
        <>
          <Text accessibilityLabel="scanner-probe-active-unmounted">Active scanner unmounted</Text>
          <Button
            title="Remount scanner"
            accessibilityLabel="scanner-probe-remount"
            onPress={() => setStage('continuation')}
          />
        </>
      )}
      {stage === 'completed' && (
        <>
          <Text accessibilityLabel="scanner-probe-completed-unmounted">Completed scanner unmounted</Text>
          <Button
            title="Report scanner check"
            accessibilityLabel="scanner-probe-report"
            onPress={() => onComplete(true)}
          />
        </>
      )}
    </CameraAccessContext.Provider>
  );
}
