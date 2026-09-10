import React, { useLayoutEffect, useRef } from 'react';
import { Platform, StyleSheet, Text, type NativeSyntheticEvent, type ViewProps } from 'react-native';
import { CameraView } from 'expo-camera';
import { requireNativeView, requireOptionalNativeModule } from 'expo';
import type { ScannerWindow } from './scannerWindow';

type WindowEvent = { allowed: boolean; generation: number };
type ScanEvent = { data: string; generation: number; scanId: number };
type NativeProps = ViewProps & {
  active: boolean;
  generation: number;
  scanId: number;
  onWindowChanged: (event: NativeSyntheticEvent<WindowEvent>) => void;
  onBarcodeScanned: (event: NativeSyntheticEvent<ScanEvent>) => void;
  onMountError: (event: NativeSyntheticEvent<Omit<ScanEvent, 'data'>>) => void;
};

const NativeScanner =
  Platform.OS === 'android' && requireOptionalNativeModule('LedovaScanner')
    ? requireNativeView<NativeProps>('LedovaScanner')
    : null;

export type ScannerPreviewProps = {
  active: boolean;
  window: ScannerWindow;
  generation: number;
  scanId: number;
  onBarcodeScanned?: (result: { data: string }) => void;
  onMountError: () => void;
};

export function ScannerPreview(props: ScannerPreviewProps) {
  const current = useRef<ScannerPreviewProps | null>(null);
  const lastWindowGeneration = useRef(-1);
  useLayoutEffect(() => {
    current.current = props;
  });
  useLayoutEffect(
    () => () => {
      current.current = null;
      if (Platform.OS === 'android') props.window.update(false, -1);
    },
    [props.window],
  );

  if (Platform.OS !== 'android') {
    return props.active ? (
      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        onBarcodeScanned={props.onBarcodeScanned}
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
      />
    ) : null;
  }
  if (!NativeScanner) return <Text>Camera unavailable. Update Ledova and try again.</Text>;

  return (
    <NativeScanner
      style={StyleSheet.absoluteFillObject}
      active={props.active}
      generation={props.generation}
      scanId={props.scanId}
      onMountError={({ nativeEvent }) => {
        const latest = current.current;
        const window = props.window.getSnapshot();
        if (
          latest?.active &&
          window.allowed &&
          window.generation === nativeEvent.generation &&
          latest.generation === nativeEvent.generation &&
          latest.scanId === nativeEvent.scanId
        ) {
          latest.onMountError();
        }
      }}
      onWindowChanged={({ nativeEvent }) => {
        if (current.current && nativeEvent.generation > lastWindowGeneration.current) {
          lastWindowGeneration.current = nativeEvent.generation;
          props.window.update(nativeEvent.allowed, nativeEvent.generation);
        }
      }}
      onBarcodeScanned={({ nativeEvent }) => {
        const latest = current.current;
        const window = props.window.getSnapshot();
        if (
          latest?.active &&
          window.allowed &&
          nativeEvent.generation === window.generation &&
          nativeEvent.scanId === latest.scanId
        ) {
          latest.onBarcodeScanned?.({ data: nativeEvent.data });
        }
      }}
    />
  );
}
