import React from 'react';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { CheckCircleIcon, WarningCircleIcon, QrCodeIcon } from 'phosphor-react-native';
import { CameraView } from 'expo-camera';
import type { PermissionResponse } from 'expo-camera';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface SignatureScanStepProps {
  permission: PermissionResponse | null;
  hasScanned: boolean;
  isVerifying: boolean;
  verificationSuccess: boolean;
  verificationError: string | null;
  onBarcodeScanned: (result: { data: string }) => void;
}

export function SignatureScanStep({
  permission,
  hasScanned,
  isVerifying,
  verificationSuccess,
  verificationError,
  onBarcodeScanned,
}: SignatureScanStepProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      gap: theme.spacing.md,
    },
    iconContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.lg,
    },
    title: {
      fontSize: theme.fontSize.xxl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      textAlign: 'center',
      marginBottom: theme.spacing.md,
    },
    cameraContainer: {
      width: '100%',
      height: 280,
      borderRadius: theme.borderRadius.lg,
      overflow: 'hidden',
      backgroundColor: theme.colors.utility.black,
      position: 'relative',
    },
    cameraMessage: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      padding: theme.spacing.xl,
    },
    cameraMessageText: {
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
      width: 220,
      height: 220,
      borderWidth: 2,
      borderColor: theme.colors.interactive.active,
      borderRadius: theme.borderRadius.md,
      backgroundColor: theme.colors.utility.transparent,
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
    errorContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: theme.spacing.sm,
      backgroundColor: theme.colors.form.errorBackground,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
    },
    errorText: {
      flex: 1,
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.text,
    },
    verifyingContainer: {
      alignItems: 'center',
      padding: theme.spacing.xl,
      gap: theme.spacing.md,
    },
    verifyingText: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.muted,
    },
    successContainer: {
      alignItems: 'center',
      gap: theme.spacing.md,
    },
    successText: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.secondary,
      textAlign: 'center',
    },
  }));
  if (verificationSuccess) {
    return (
      <View style={styles.container}>
        <View style={styles.successContainer}>
          <View style={styles.iconContainer}>
            <CheckCircleIcon
              size={theme.icon.sizes.xxl}
              weight={theme.icon.weights.light}
              color={theme.colors.status.success.icon}
            />
          </View>
          <Text style={styles.title}>Verification Successful!</Text>
          <Text style={styles.successText}>Your wallet ownership has been verified.</Text>
        </View>
      </View>
    );
  }

  if (isVerifying) {
    return (
      <View style={styles.container}>
        <View style={styles.verifyingContainer}>
          <ActivityIndicator size="large" color={theme.colors.interactive.default} />
          <Text style={styles.verifyingText}>Verifying signature...</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.iconContainer}>
        <QrCodeIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
      </View>

      <Text style={styles.title}>Scan Signature QR</Text>

      <View style={styles.cameraContainer}>
        {!permission ? (
          <View style={styles.cameraMessage}>
            <Text style={styles.cameraMessageText}>Requesting camera permission...</Text>
          </View>
        ) : !permission.granted ? (
          <View style={styles.cameraMessage}>
            <Text style={styles.cameraMessageText}>
              Camera permission is required to scan QR codes. Please enable it in settings.
            </Text>
          </View>
        ) : (
          <>
            <CameraView
              style={StyleSheet.absoluteFillObject}
              facing="back"
              onBarcodeScanned={hasScanned ? undefined : onBarcodeScanned}
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

      {verificationError && (
        <View style={styles.errorContainer}>
          <WarningCircleIcon
            size={theme.icon.sizes.md}
            color={theme.colors.status.error.icon}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.errorText}>{verificationError}</Text>
        </View>
      )}
    </View>
  );
}
