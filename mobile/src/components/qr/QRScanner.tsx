import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { CameraView } from 'expo-camera';
import { QrCodeIcon } from 'phosphor-react-native';

import { useAppTheme, useThemedStyles } from '../../contexts';
import { CustomModal } from '../modal';
import { useCameraScanner } from './useCameraScanner';
import { CameraWindow } from './CameraWindow';

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
  }));
  const camera = useCameraScanner(visible, (data, finishScan) => {
    finishScan();
    onScan(data);
  });

  const handleClose = () => {
    camera.stop();
    onClose();
  };

  if (!visible) return null;

  return (
    <CustomModal visible={visible} onClose={handleClose} showFooter={true} cancelLabel="Cancel">
      <View style={styles.headerContainer}>
        <QrCodeIcon size={48} color={theme.colors.status.info.icon} weight="regular" style={styles.icon} />
        <Text style={styles.title}>{title}</Text>
        {subtitle && <Text style={styles.subtitle}>{subtitle}</Text>}
      </View>

      <CameraWindow access={camera.windowAccess} style={styles.cameraContainer}>
        {camera.message ? (
          <View style={styles.messageContainer}>
            <Text style={styles.message}>{camera.message}</Text>
          </View>
        ) : (
          <>
            <CameraView
              key={camera.previewKey}
              style={StyleSheet.absoluteFillObject}
              facing="back"
              onBarcodeScanned={camera.onBarcodeScanned}
              barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
            />
            <View style={styles.cameraOverlay}>
              <View style={styles.scanArea} />
            </View>
          </>
        )}
      </CameraWindow>

      {camera.status === 'ready' && <Text style={styles.instructionText}>Position the QR code within the frame</Text>}
    </CustomModal>
  );
}
