import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { URDecoder, UREncoder } from '@ngraveio/bc-ur';
import { useAppTheme, useThemedStyles } from '../../contexts';

interface AnimatedQRScannerProps {
  onComplete: (urString: string) => void;
}

export function AnimatedQRScanner({ onComplete }: AnimatedQRScannerProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      width: 300,
      height: 300,
      borderRadius: theme.borderRadius.lg,
      overflow: 'hidden',
      backgroundColor: theme.colors.surface.raised,
      alignItems: 'center',
      justifyContent: 'center',
    },
    message: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      padding: theme.spacing.lg,
    },
    overlay: {
      ...StyleSheet.absoluteFillObject,
      alignItems: 'center',
      justifyContent: 'center',
    },
    scanArea: {
      width: 250,
      height: 250,
      borderWidth: 2,
      borderColor: theme.colors.interactive.defaultSubtle,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.utility.transparent,
    },
    progressIndicator: {
      position: 'absolute',
      top: theme.spacing.md,
      left: 0,
      right: 0,
      alignItems: 'center',
    },
    progressText: {
      backgroundColor: theme.colors.interactive.default,
      color: theme.colors.utility.white,
      paddingHorizontal: theme.spacing.lg,
      paddingVertical: theme.spacing.sm,
      borderRadius: theme.borderRadius.md,
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.semibold,
    },
  }));
  const [permission, requestPermission] = useCameraPermissions();
  const [progress, setProgress] = useState<{ received: number; total: number } | null>(null);
  const decoderRef = useRef<URDecoder | null>(null);
  const processedPartsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    decoderRef.current = new URDecoder();
    processedPartsRef.current = new Set();

    if (!permission) {
      requestPermission();
    }

    return () => {
      decoderRef.current = null;
      processedPartsRef.current.clear();
    };
  }, [permission, requestPermission]);

  const handleBarCodeScanned = ({ data }: { data: string }) => {
    const dataLower = data.toLowerCase();

    if (!dataLower.startsWith('ur:')) {
      onComplete(data);
      return;
    }

    if (!decoderRef.current || processedPartsRef.current.has(dataLower)) {
      return;
    }

    processedPartsRef.current.add(dataLower);

    try {
      decoderRef.current.receivePart(dataLower);

      const estimatedPercentComplete = decoderRef.current.estimatedPercentComplete();
      const receivedParts = processedPartsRef.current.size;
      setProgress({
        received: receivedParts,
        total: estimatedPercentComplete > 0 ? Math.ceil(receivedParts / estimatedPercentComplete) : receivedParts,
      });

      if (decoderRef.current.isComplete()) {
        const ur = decoderRef.current.resultUR();
        // Use a large fragment size to ensure the entire UR fits in one part
        const encoder = new UREncoder(ur, 100000);
        const completeURString = encoder.nextPart();
        onComplete(completeURString);
      }
    } catch {
      // Silently handle error
    }
  };

  if (!permission) {
    return (
      <View style={styles.container}>
        <Text style={styles.message}>Requesting camera permission...</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.container}>
        <Text style={styles.message}>
          Camera permission is required to scan QR codes. Please enable it in settings.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        onBarcodeScanned={handleBarCodeScanned}
        barcodeScannerSettings={{
          barcodeTypes: ['qr'],
        }}
      />
      <View style={styles.overlay}>
        <View style={styles.scanArea} />
      </View>
      {progress && (
        <View style={styles.progressIndicator}>
          <Text style={styles.progressText}>
            Scanning: {progress.received}/{progress.total > 0 ? progress.total : '?'} parts
          </Text>
        </View>
      )}
    </View>
  );
}
