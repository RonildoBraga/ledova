import React from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { QrCodeIcon } from 'phosphor-react-native';
import { QRDisplay } from '../../../components/qr';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface ChallengeQRStepProps {
  urEncodedChallenge: string | null;
}

export function ChallengeQRStep({ urEncodedChallenge }: ChallengeQRStepProps) {
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
    loadingContainer: {
      alignItems: 'center',
      justifyContent: 'center',
      padding: theme.spacing.xl * 2,
      gap: theme.spacing.md,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
  }));
  return (
    <View style={styles.container}>
      <View style={styles.iconContainer}>
        <QrCodeIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
      </View>

      <Text style={styles.title}>Scan Challenge QR</Text>

      {urEncodedChallenge ? (
        <QRDisplay data={urEncodedChallenge} isUR={true} />
      ) : (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.interactive.default} />
          <Text style={styles.loadingText}>Generating challenge QR...</Text>
        </View>
      )}
    </View>
  );
}
