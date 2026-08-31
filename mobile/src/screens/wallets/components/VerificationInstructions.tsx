import React from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { CheckCircleIcon, WarningCircleIcon, ShieldCheckIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface VerificationInstructionsProps {
  isSoftwareWallet: boolean;
  isRequestingChallenge: boolean;
  isVerifying: boolean;
  verificationSuccess: boolean;
  verificationError: string | null;
}

export function VerificationInstructions({
  isSoftwareWallet,
  isRequestingChallenge,
  isVerifying,
  verificationSuccess,
  verificationError,
}: VerificationInstructionsProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    instructionsContainer: {
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
    instructions: {
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.lg,
    },
    instructionTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.md,
    },
    instructionText: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.secondary,
      lineHeight: theme.lineHeight.relaxed * theme.fontSize.base,
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
    successText: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.secondary,
      textAlign: 'center',
    },
  }));
  if (isSoftwareWallet) {
    return (
      <View style={styles.instructionsContainer}>
        <View style={styles.iconContainer}>
          {verificationSuccess ? (
            <CheckCircleIcon
              size={theme.icon.sizes.xxl}
              weight={theme.icon.weights.light}
              color={theme.colors.status.success.icon}
            />
          ) : isRequestingChallenge || isVerifying ? (
            <ActivityIndicator size="large" color={theme.colors.interactive.default} />
          ) : (
            <ShieldCheckIcon
              size={theme.icon.sizes.xxl}
              color={theme.colors.status.info.icon}
              weight={theme.icon.weights.light}
            />
          )}
        </View>
        <Text style={styles.title}>
          {verificationSuccess
            ? 'Verification Successful!'
            : isRequestingChallenge || isVerifying
              ? 'Verifying...'
              : 'Verify Wallet'}
        </Text>
        {verificationSuccess && <Text style={styles.successText}>Your wallet ownership has been verified.</Text>}
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

  return (
    <View style={styles.instructionsContainer}>
      <View style={styles.iconContainer}>
        <ShieldCheckIcon
          size={theme.icon.sizes.xxl}
          color={theme.colors.status.info.icon}
          weight={theme.icon.weights.light}
        />
      </View>

      <Text style={styles.title}>Verify Wallet Ownership</Text>

      <View style={styles.instructions}>
        <Text style={styles.instructionTitle}>How verification works:</Text>
        <Text style={styles.instructionText}>
          1. We&apos;ll generate a unique verification challenge{'\n'}
          2. Scan the challenge QR with your hardware wallet{'\n'}
          3. Review and sign the message on your device{'\n'}
          4. Scan the signature QR back to the app{'\n'}
          5. Your wallet will be verified!
        </Text>
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
