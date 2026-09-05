import React from 'react';
import { View, Text, ActivityIndicator, ScrollView } from 'react-native';
import { QRDisplay } from '../../../components/qr';
import { useAppTheme, useThemedStyles } from '../../../contexts';

interface SignTransactionProps {
  urEncodedTransaction: string | null;
}

export function SignTransaction({ urEncodedTransaction }: SignTransactionProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    scrollContent: {
      flex: 1,
    },
    scrollContentContainer: {
      paddingHorizontal: theme.spacing.md,
      paddingTop: theme.spacing.md,
      paddingBottom: theme.spacing.md,
    },
    section: {
      gap: theme.spacing.sm,
      marginBottom: theme.spacing.md,
    },
    sectionTitle: {
      fontSize: theme.fontSize.xs,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.secondary,
      textTransform: 'uppercase',
      letterSpacing: 0.5,
      textAlign: 'center',
    },
    qrContainer: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.sm,
      minHeight: 200,
    },
    qrLoading: {
      alignItems: 'center',
      gap: theme.spacing.md,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    dividerContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      marginVertical: theme.spacing.md,
    },
    dividerLine: {
      flex: 1,
      height: 1,
      backgroundColor: theme.colors.border.default,
    },
    dividerText: {
      marginHorizontal: theme.spacing.md,
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      fontWeight: theme.fontWeight.medium,
    },
    instructionsContainer: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      borderWidth: 1,
      borderColor: theme.colors.border.subtle,
    },
    instructionsText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      lineHeight: 20,
      textAlign: 'center',
    },
  }));
  return (
    <ScrollView
      style={styles.scrollContent}
      contentContainerStyle={styles.scrollContentContainer}
      showsVerticalScrollIndicator={false}
    >
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Scan with your Wallet</Text>
        <View style={styles.qrContainer}>
          {urEncodedTransaction ? (
            <QRDisplay data={urEncodedTransaction} isUR />
          ) : (
            <View style={styles.qrLoading}>
              <ActivityIndicator size="large" color={theme.colors.interactive.active} />
              <Text style={styles.loadingText}>Generating QR code...</Text>
            </View>
          )}
        </View>
      </View>

      <View style={styles.dividerContainer}>
        <View style={styles.dividerLine} />
        <Text style={styles.dividerText}>then scan signature</Text>
        <View style={styles.dividerLine} />
      </View>

      <View style={styles.instructionsContainer}>
        <Text style={styles.instructionsText}>
          After signing the transaction on your hardware wallet, scan the signature QR code using the button below.
        </Text>
      </View>
    </ScrollView>
  );
}
