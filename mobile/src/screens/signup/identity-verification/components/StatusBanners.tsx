import React from 'react';
import { View, Text } from 'react-native';
import {
  CheckCircleIcon,
  WarningCircleIcon,
  ClockCountdownIcon,
  ArrowCounterClockwiseIcon,
} from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../../contexts';

interface StatusBannersProps {
  isVerified: boolean;
  showPendingBanner: boolean;
  showOnHoldBanner: boolean;
  showRejectedBanner: boolean;
  showRetryBanner: boolean;
  rejectionLabels?: string[] | null;
}

export function StatusBanners({
  isVerified,
  showPendingBanner,
  showOnHoldBanner,
  showRejectedBanner,
  showRetryBanner,
  rejectionLabels,
}: StatusBannersProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    successContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.xl,
      paddingHorizontal: theme.spacing.lg,
      backgroundColor: `${theme.colors.status.success.icon}20`,
      borderWidth: 1,
      borderColor: theme.colors.badge.success.background,
      borderRadius: theme.borderRadius.lg,
      marginBottom: theme.spacing.lg,
    },
    successTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.status.success.text,
      marginTop: theme.spacing.sm,
    },
    pendingContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.xl,
      paddingHorizontal: theme.spacing.lg,
      backgroundColor: `${theme.colors.interactive.active}20`,
      borderWidth: 1,
      borderColor: theme.colors.interactive.active,
      borderRadius: theme.borderRadius.lg,
      marginBottom: theme.spacing.lg,
    },
    pendingTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.interactive.active,
      marginTop: theme.spacing.sm,
    },
    warningContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.xl,
      paddingHorizontal: theme.spacing.lg,
      backgroundColor: `${theme.colors.status.warning.icon}15`,
      borderWidth: 1,
      borderColor: `${theme.colors.status.warning.icon}40`,
      borderRadius: theme.borderRadius.lg,
      marginBottom: theme.spacing.lg,
    },
    warningTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.status.warning.text,
      marginTop: theme.spacing.sm,
    },
    rejectedContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.xl,
      paddingHorizontal: theme.spacing.lg,
      backgroundColor: theme.colors.error.backgroundSubtle,
      borderWidth: 1,
      borderColor: theme.colors.form.borderError,
      borderRadius: theme.borderRadius.lg,
      marginBottom: theme.spacing.lg,
    },
    rejectedTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.form.error,
      marginTop: theme.spacing.sm,
    },
    bannerText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
      textAlign: 'center',
      marginTop: theme.spacing.xs,
    },
    rejectionReasons: {
      marginTop: theme.spacing.sm,
      width: '100%',
    },
    reasonsLabel: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      textTransform: 'uppercase',
      marginTop: theme.spacing.sm,
    },
    reasonItem: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
      marginTop: theme.spacing.xs,
    },
  }));
  return (
    <>
      {isVerified && (
        <View style={styles.successContainer}>
          <CheckCircleIcon
            size={theme.icon.sizes.md}
            color={theme.colors.status.success.icon}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.successTitle}>Already Verified</Text>
          <Text style={styles.bannerText}>Your identity has been verified successfully.</Text>
        </View>
      )}

      {showPendingBanner && (
        <View style={styles.pendingContainer}>
          <CheckCircleIcon
            size={theme.icon.sizes.md}
            color={theme.colors.interactive.active}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.pendingTitle}>Verification Submitted</Text>
          <Text style={styles.bannerText}>
            Your documents have been submitted. We&apos;ll review them shortly and notify you of the result.
          </Text>
        </View>
      )}

      {showOnHoldBanner && (
        <View style={styles.warningContainer}>
          <ClockCountdownIcon
            size={theme.icon.sizes.md}
            color={theme.colors.status.warning.icon}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.warningTitle}>Verification On Hold</Text>
          <Text style={styles.bannerText}>
            Your verification is currently on hold. We may need additional information. Please check back later or
            contact support.
          </Text>
        </View>
      )}

      {showRejectedBanner && (
        <View style={styles.rejectedContainer}>
          <WarningCircleIcon
            size={theme.icon.sizes.md}
            color={theme.colors.status.error.icon}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.rejectedTitle}>Verification Rejected</Text>
          <Text style={styles.bannerText}>
            Unfortunately, your verification was not approved. You may retry with different documents or contact support
            for assistance.
          </Text>
          <RejectionReasons labels={rejectionLabels} />
        </View>
      )}

      {showRetryBanner && (
        <View style={styles.warningContainer}>
          <ArrowCounterClockwiseIcon
            size={theme.icon.sizes.md}
            color={theme.colors.status.warning.icon}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.warningTitle}>Retry Needed</Text>
          <Text style={styles.bannerText}>
            Your previous verification attempt needs to be retried. Please try again with clearer documents.
          </Text>
          <RejectionReasons labels={rejectionLabels} />
        </View>
      )}
    </>
  );
}

function RejectionReasons({ labels }: { labels?: string[] | null }) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    rejectionReasons: {
      marginTop: theme.spacing.sm,
      width: '100%',
    },
    reasonsLabel: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      textTransform: 'uppercase',
      marginTop: theme.spacing.sm,
    },
    reasonItem: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
      marginTop: theme.spacing.xs,
    },
  }));
  if (!labels || labels.length === 0) return null;

  return (
    <View style={styles.rejectionReasons}>
      <Text style={styles.reasonsLabel}>Reasons:</Text>
      {labels.map((label, index) => (
        <Text key={index} style={styles.reasonItem}>
          {'\u2022'} {label}
        </Text>
      ))}
    </View>
  );
}
