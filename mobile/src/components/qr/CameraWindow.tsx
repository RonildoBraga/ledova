import React, { useId, useLayoutEffect } from 'react';
import { Platform, View, type ViewProps } from 'react-native';
import { requireNativeView } from 'expo';
import type { CameraWindowAccess } from './cameraWindowAccess';

interface NativeWindowProps extends ViewProps {
  ownerId: string;
  onWindowChange: (event: { nativeEvent: unknown }) => void;
}

let nativeWindow: React.ComponentType<NativeWindowProps> | undefined;

export function CameraWindow({ access, ...props }: ViewProps & { access: CameraWindowAccess }) {
  const instanceId = useId();
  const ownerId = `${instanceId}:${access.sessionKey}`;
  const android = Platform.OS === 'android';
  useLayoutEffect(() => {
    if (!android) return;
    access.attach(ownerId);
    return () => access.detach(ownerId);
  }, [access, android, ownerId]);

  if (!android) return <View {...props} />;
  nativeWindow ??= requireNativeView<NativeWindowProps>('LedovaCameraWindow');
  const NativeWindow = nativeWindow;
  return (
    <NativeWindow
      {...props}
      testID="camera-window"
      ownerId={ownerId}
      onWindowChange={({ nativeEvent }) => access.update(ownerId, nativeEvent)}
    />
  );
}
