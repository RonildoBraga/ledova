import { useEffect, useRef, useState, type Ref } from 'react';
import { Modal, View, Text, Platform, type ViewProps } from 'react-native';
import { requireNativeView } from 'expo';
import { CameraAccessContext, createCameraAccess } from '../src/contexts/cameraAccess';
import { ScannerPreview } from '../src/components/qr/ScannerPreview';
import { useCameraScanner } from '../src/components/qr/useCameraScanner';

type Props = { onComplete: (passed: boolean) => void };
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
  useEffect(() => {
    native.current
      ?.isCurrentScan(-1, 0)
      .then((allowed) => (allowed ? onComplete(false) : setMethodReady(true)))
      .catch(() => onComplete(false));
  }, [onComplete]);
  useEffect(() => {
    const deadline = setTimeout(() => onComplete(false), 25000);
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
        <InactiveProbe ref={native} active={false} generation={-1} scanId={0} style={{ width: 1, height: 1 }} />
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
