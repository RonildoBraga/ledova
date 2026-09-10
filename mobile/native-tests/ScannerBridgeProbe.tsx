import { useEffect, useState } from 'react';
import { Modal, View, Text } from 'react-native';
import { CameraAccessContext, createCameraAccess } from '../src/contexts/cameraAccess';
import { ScannerPreview } from '../src/components/qr/ScannerPreview';
import { useCameraScanner } from '../src/components/qr/useCameraScanner';

type Props = { onComplete: (passed: boolean) => void };

function WindowProbe({ onComplete }: Props) {
  const camera = useCameraScanner(true, () => {});
  const [stage, setStage] = useState<'opening' | 'covered' | 'returning'>('opening');
  const [firstGeneration, setFirstGeneration] = useState(-1);
  useEffect(() => {
    const deadline = setTimeout(() => onComplete(false), 25000);
    return () => clearTimeout(deadline);
  }, [onComplete]);
  useEffect(() => {
    if (stage === 'opening' && camera.status === 'ready') {
      setFirstGeneration(camera.preview.generation);
      setStage('covered');
    } else if (stage === 'covered' && camera.status === 'inactive') {
      setStage('returning');
    } else if (stage === 'returning' && camera.status === 'ready') {
      onComplete(camera.preview.generation > firstGeneration);
    }
  }, [stage, camera.status, camera.preview.generation, firstGeneration, onComplete]);

  return (
    <Modal visible animationType="none">
      <View style={{ width: 240, height: 240 }}>
        <ScannerPreview {...camera.preview} />
        <Text>{camera.status}</Text>
      </View>
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
