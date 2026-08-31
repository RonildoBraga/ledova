import React, { useEffect } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { ShieldCheckIcon, WarningCircleIcon } from 'phosphor-react-native';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useIdentityVerification } from '../../../hooks/useIdentityVerification';
import { CustomModal } from '../../../components/modal';
import { PrimaryButton } from '../../../components/buttons';
import { StatusBanners } from '../../signup/identity-verification/components/StatusBanners';
import { VerificationFormModal } from '../../signup/identity-verification/components/VerificationFormModal';

interface VerificationModalProps {
  visible: boolean;
  onClose: () => void;
  onRefresh: () => void;
}

export function VerificationModal({ visible, onClose, onRefresh }: VerificationModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    modalHeader: {
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
    },
    modalIconStyle: {
      marginBottom: theme.spacing.md,
    },
    modalTitle: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.sm,
      textAlign: 'center',
    },
    modalSubtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      lineHeight: theme.lineHeight.normal * theme.fontSize.sm,
    },
    modalLoading: {
      alignItems: 'center',
      paddingVertical: theme.spacing.xl,
    },
    modalLoadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      marginTop: theme.spacing.md,
    },
    modalError: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.error.backgroundSubtle,
      borderWidth: 1,
      borderColor: theme.colors.form.borderError,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      marginBottom: theme.spacing.lg,
    },
    modalErrorText: {
      flex: 1,
      fontSize: theme.fontSize.sm,
      color: theme.colors.form.error,
      marginLeft: theme.spacing.sm,
    },
    retryButtonContainer: {
      marginTop: theme.spacing.md,
      width: '100%',
    },
    infoBox: {
      padding: theme.spacing.lg,
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
    },
    infoBoxTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.md,
    },
    infoBoxList: {
      gap: theme.spacing.sm,
    },
    infoBoxItem: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.secondary,
      lineHeight: theme.lineHeight.normal * theme.fontSize.sm,
    },
  }));
  const {
    status,
    isLoadingStatus,
    launchVerification,
    isLaunching,
    sdkError,
    clearError,
    isPending,
    isOnHold,
    isRejected,
    needsRetry,
    hasSubmitted,
    justSubmitted,
    isVerified,
    resetState,
    accessToken,
    formUrl,
    showVerificationForm,
    handleFormComplete,
    closeFormModal,
  } = useIdentityVerification();

  useEffect(() => {
    if (visible) {
      resetState();
    }
  }, [visible, resetState]);

  useEffect(() => {
    if (justSubmitted && visible) {
      const timer = setTimeout(() => {
        onClose();
        onRefresh();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [justSubmitted, visible, onClose, onRefresh]);

  const handleStartVerification = async () => {
    try {
      await launchVerification();
    } catch {
      // The hook exposes the launch error in modal state.
    }
  };

  const handleClose = () => {
    clearError();
    onClose();
  };

  const showStatusBanner = justSubmitted || hasSubmitted || isPending || isOnHold || isRejected || isVerified;
  const showInitialPhase = !showStatusBanner && !isLoadingStatus;
  const showModalFooter = showInitialPhase && !isLaunching;

  const showPendingBanner = (justSubmitted || (isPending && !isVerified)) && !isRejected;
  const showOnHoldBanner = isOnHold && !justSubmitted;
  const showRejectedBanner = isRejected && !justSubmitted && !needsRetry;
  const showRetryBanner = needsRetry && !isVerified && !justSubmitted;

  return (
    <>
      <CustomModal
        visible={visible && !showVerificationForm}
        onClose={handleClose}
        showFooter={showModalFooter}
        cancelLabel="Skip"
        confirmLabel="Start"
        onConfirm={handleStartVerification}
        confirmLoading={isLaunching}
        confirmDisabled={isLaunching}
      >
        <View style={styles.modalHeader}>
          <ShieldCheckIcon
            size={theme.icon.sizes.xxl}
            color={theme.colors.interactive.active}
            weight={theme.icon.weights.regular}
            style={styles.modalIconStyle}
          />
          <Text style={styles.modalTitle}>Identity Verification</Text>
          <Text style={styles.modalSubtitle}>
            We need to verify your identity to comply with financial regulations and protect your account.
          </Text>
        </View>

        {(isLaunching || isLoadingStatus) && (
          <View style={styles.modalLoading}>
            <ActivityIndicator size="large" color={theme.colors.interactive.active} />
            <Text style={styles.modalLoadingText}>
              {isLaunching ? 'Preparing verification...' : 'Loading status...'}
            </Text>
          </View>
        )}

        {sdkError && (
          <View style={styles.modalError}>
            <WarningCircleIcon size={theme.icon.sizes.md} color={theme.colors.status.error.icon} weight="regular" />
            <Text style={styles.modalErrorText}>{sdkError}</Text>
          </View>
        )}

        <StatusBanners
          isVerified={isVerified}
          showPendingBanner={showPendingBanner}
          showOnHoldBanner={showOnHoldBanner}
          showRejectedBanner={showRejectedBanner}
          showRetryBanner={showRetryBanner}
          rejectionLabels={status?.rejectionLabels}
        />

        {showRetryBanner && (
          <View style={styles.retryButtonContainer}>
            <PrimaryButton onPress={handleStartVerification} loading={isLaunching} fullWidth>
              Retry Verification
            </PrimaryButton>
          </View>
        )}

        {showInitialPhase && !isLaunching && (
          <View style={styles.infoBox}>
            <Text style={styles.infoBoxTitle}>What You&apos;ll Need:</Text>
            <View style={styles.infoBoxList}>
              <Text style={styles.infoBoxItem}>{'\u2022'} A valid government-issued ID</Text>
              <Text style={styles.infoBoxItem}>{'\u2022'} Good lighting for clear photos</Text>
              <Text style={styles.infoBoxItem}>{'\u2022'} About 3-5 minutes</Text>
            </View>
          </View>
        )}
      </CustomModal>

      <VerificationFormModal
        visible={showVerificationForm}
        accessToken={accessToken}
        formUrl={formUrl}
        onComplete={handleFormComplete}
        onClose={closeFormModal}
      />
    </>
  );
}
