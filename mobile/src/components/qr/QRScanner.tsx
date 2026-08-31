import React, { useState, useEffect, useCallback, useRef } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { QrCodeIcon } from 'phosphor-react-native';

import { useAppTheme, useThemedStyles } from '../../contexts';
import { CustomModal } from '../modal';

interface QRScannerProps {
  visible: boolean;
  onClose: () => void;
  onScan: (data: string) => void;
  title?: string;
  subtitle?: string;
}

export function QRScanner({ visible, onClose, onScan, title = 'Scan QR Code', subtitle }: QRScannerProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    headerContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
      gap: theme.spacing.sm,
    },
    icon: {
      marginBottom: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      textAlign: 'center',
    },
    subtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      marginBottom: theme.spacing.sm,
    },
    cameraContainer: {
      width: '100%',
      height: 320,
      borderRadius: theme.borderRadius.lg,
      overflow: 'hidden',
      backgroundColor: theme.colors.utility.black,
      position: 'relative',
      marginBottom: theme.spacing.md,
    },
    messageContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: theme.spacing.xl,
    },
    message: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    cameraOverlay: {
      ...StyleSheet.absoluteFillObject,
      alignItems: 'center',
      justifyContent: 'center',
    },
    scanArea: {
      width: 260,
      height: 260,
      borderWidth: 2,
      borderColor: theme.colors.interactive.active,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.utility.transparent,
    },
    instructionText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
    },
    scannedIndicator: {
      position: 'absolute',
      top: theme.spacing.md,
      left: 0,
      right: 0,
      alignItems: 'center',
    },
    scannedText: {
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
  const [hasScanned, setHasScanned] = useState(false);
  // Use ref to immediately block subsequent scans (state updates are async)
  const scanLockRef = useRef(false);

  useEffect(() => {
    if (!permission) {
      requestPermission();
    }
  }, [permission, requestPermission]);

  useEffect(() => {
    if (visible) {
      setHasScanned(false);
      scanLockRef.current = false;
    }
  }, [visible]);

  const handleBarCodeScanned = useCallback(
    ({ data }: { data: string }) => {
      // Use ref for immediate check (synchronous) to prevent multiple calls
      if (scanLockRef.current) return;
      scanLockRef.current = true;
      setHasScanned(true);
      onScan(data);
    },
    [onScan],
  );

  const handleClose = useCallback(() => {
    setHasScanned(false);
    scanLockRef.current = false;
    onClose();
  }, [onClose]);

  return (
    <CustomModal visible={visible} onClose={handleClose} showFooter={true} cancelLabel="Cancel">
      <View style={styles.headerContainer}>
        <QrCodeIcon size={48} color={theme.colors.status.info.icon} weight="regular" style={styles.icon} />
        <Text style={styles.title}>{title}</Text>
        {subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      </View>

      <View style={styles.cameraContainer}>
        {!permission ? (
          <View style={styles.messageContainer}>
            <Text style={styles.message}>Requesting camera permission...</Text>
          </View>
        ) : !permission.granted ? (
          <View style={styles.messageContainer}>
            <Text style={styles.message}>
              Camera permission is required to scan QR codes. Please enable it in settings.
            </Text>
          </View>
        ) : (
          <>
            <CameraView
              style={StyleSheet.absoluteFillObject}
              facing="back"
              onBarcodeScanned={hasScanned ? undefined : handleBarCodeScanned}
              barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
            />
            <View style={styles.cameraOverlay}>
              <View style={styles.scanArea} />
            </View>
            {hasScanned && (
              <View style={styles.scannedIndicator}>
                <Text style={styles.scannedText}>✓ Scanned!</Text>
              </View>
            )}
          </>
        )}
      </View>

      {permission?.granted && <Text style={styles.instructionText}>Position the QR code within the frame</Text>}
    </CustomModal>
  );
}
