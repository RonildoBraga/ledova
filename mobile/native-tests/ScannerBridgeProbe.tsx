import { useEffect, useRef, useState, type Ref } from 'react';
import { Modal, View, Text, Platform, type ViewProps } from 'react-native';
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

function WindowProbe({ onComplete }: Props) {
  const camera = useCameraScanner(true, () => {});
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
    const deadline = setTimeout(() => onComplete(false, 'window-timeout'), 25000);
    return () => clearTimeout(deadline);
  }, [onComplete]);
  useEffect(() => {
    if (stage === 'opening' && camera.status === 'ready' && methodReady) {
      setFirstGeneration(camera.preview.generation);
      setStage('covered');
    } else if (stage === 'covered' && camera.status === 'inactive') {
      setStage('returning');
    } else if (stage === 'returning' && camera.status === 'ready') {
      onComplete(camera.preview.generation > firstGeneration);
    }
  }, [stage, camera.status, camera.preview.generation, firstGeneration, methodReady, onComplete]);

  return (
    <Modal visible animationType="none">
      <View style={{ width: 240, height: 240 }}>
        <ScannerPreview {...camera.preview} />
        <Text>{camera.status}</Text>
      </View>
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
        <View>
          <Text>Synthetic scanner window cover</Text>
        </View>
      </Modal>
    </Modal>
  );
}

export function ScannerBridgeProbe(props: Props) {
  const [access] = useState(() => {
    const value = createCameraAccess();
    value.setAllowed(true);
    return value;
  });
  return (
    <CameraAccessContext.Provider value={access}>
      <WindowProbe {...props} />
    </CameraAccessContext.Provider>
  );
}
