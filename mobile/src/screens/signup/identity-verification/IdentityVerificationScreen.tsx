import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { GradientBackground } from '../../../components/GradientBackground';
import { PrimaryButton, SecondaryButton } from '../../../components/buttons';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import type { RootStackParamList } from '../../../navigation/AppNavigator';
import { useIdentityVerification } from './useIdentityVerification';
import { StatusBanners } from './components/StatusBanners';
import { VerificationFormModal } from './components/VerificationFormModal';
import { ShieldCheckIcon, WarningCircleIcon } from 'phosphor-react-native';
import { layout } from '../../../styles';
import { useAppTheme, useThemedStyles } from '../../../contexts';

export function IdentityVerificationScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    scrollContent: {
      flexGrow: 1,
      justifyContent: 'center',
      paddingHorizontal: theme.spacing.sm,
      paddingTop: theme.spacing.xs,
      paddingBottom: layout.screenBottomPadding,
    },
    header: {
      alignItems: 'center',
      marginTop: theme.spacing.xs,
      marginBottom: theme.spacing.md,
    },
    iconContainer: {
      padding: theme.spacing.xs,
      marginBottom: theme.spacing.sm,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.xs,
      textAlign: 'center',
    },
    subtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      lineHeight: theme.lineHeight.normal * theme.fontSize.sm,
      textAlign: 'center',
      paddingHorizontal: theme.spacing.md,
    },
    formContainer: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      padding: theme.spacing.lg,
    },
    loadingContainer: {
      alignItems: 'center',
      paddingVertical: theme.spacing.xl,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      marginTop: theme.spacing.md,
    },
    errorContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.error.backgroundSubtle,
      borderWidth: 1,
      borderColor: theme.colors.form.borderError,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      marginBottom: theme.spacing.lg,
    },
    errorText: {
      flex: 1,
      fontSize: theme.fontSize.sm,
      color: theme.colors.form.error,
      marginLeft: theme.spacing.sm,
    },
    infoBox: {
      padding: theme.spacing.lg,
      backgroundColor: theme.colors.surface.tertiary,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      marginBottom: theme.spacing.lg,
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
    buttonContainer: {
      marginTop: theme.spacing.md,
      gap: theme.spacing.md,
    },
    divider: {
      flexDirection: 'row',
      alignItems: 'center',
      marginVertical: theme.spacing.xl,
    },
    dividerLine: {
      flex: 1,
      height: 1,
      backgroundColor: theme.colors.border.default,
    },
    dividerText: {
      marginHorizontal: theme.spacing.md,
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.subtle,
      fontWeight: theme.fontWeight.medium,
    },
    backLink: {
      alignItems: 'center',
      paddingVertical: theme.spacing.md,
    },
    backLinkText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.semibold,
    },
  }));
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();

  const {
    status,
    isLoadingStatus,
    isVerified,
    tokenError,
    sdkError,
    launchVerification,
    prepareForNextScreen,
    isLaunching,
    isContinuing,
    hasApplicant,
    accessToken,
    formUrl,
    showVerificationForm,
    handleFormComplete,
    closeFormModal,
    showPendingBanner,
    showOnHoldBanner,
    showRejectedBanner,
    showRetryBanner,
    showForm,
    showContinue,
    showSkip,
  } = useIdentityVerification();

  const handleContinue = async () => {
    const success = await prepareForNextScreen();
    if (success) {
      navigation.navigate('UserProfile');
    }
  };

  const handleSkipForNow = () => {
    navigation.navigate('UserProfile');
  };

  const handleBack = () => {
    navigation.navigate('PreScreening');
  };

  return (
    <GradientBackground>
      <SafeAreaView style={styles.container}>
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <View style={styles.header}>
            <View style={styles.iconContainer}>
              <ShieldCheckIcon
                size={theme.icon.sizes.md}
                color={theme.colors.text.muted}
                weight={theme.icon.weights.regular}
              />
            </View>
            <Text style={styles.title}>Identity Verification</Text>
            <Text style={styles.subtitle}>
              We need to verify your identity to comply with financial regulations and protect your account.
            </Text>
          </View>

          <View style={styles.formContainer}>
            {(isLoadingStatus || isLaunching) && (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color={theme.colors.interactive.active} />
                <Text style={styles.loadingText}>
                  {isLaunching ? 'Preparing verification...' : 'Loading status...'}
                </Text>
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

            {(sdkError || tokenError) && (
              <View style={styles.errorContainer}>
                <WarningCircleIcon
                  size={theme.icon.sizes.md}
                  color={theme.colors.status.error.icon}
                  weight={theme.icon.weights.regular}
                />
                <Text style={styles.errorText}>{sdkError || tokenError?.message || 'An error occurred'}</Text>
              </View>
            )}

            {showForm && !isLoadingStatus && !hasApplicant && (
              <View style={styles.infoBox}>
                <Text style={styles.infoBoxTitle}>What You&apos;ll Need:</Text>
                <View style={styles.infoBoxList}>
                  <Text style={styles.infoBoxItem}>{'\u2022'} A valid government-issued ID</Text>
                  <Text style={styles.infoBoxItem}>{'\u2022'} Good lighting for clear photos</Text>
                  <Text style={styles.infoBoxItem}>{'\u2022'} About 3-5 minutes</Text>
                </View>
              </View>
            )}

            <View style={styles.buttonContainer}>
              {showForm && (
                <PrimaryButton onPress={launchVerification} loading={isLaunching} disabled={isLoadingStatus} fullWidth>
                  {hasApplicant ? 'Continue Verification' : 'Start Verification'}
                </PrimaryButton>
              )}

              {showRetryBanner && (
                <PrimaryButton onPress={launchVerification} loading={isLaunching} disabled={isLoadingStatus} fullWidth>
                  Retry Verification
                </PrimaryButton>
              )}

              {showContinue && (
                <PrimaryButton onPress={handleContinue} loading={isContinuing} fullWidth>
                  Continue
                </PrimaryButton>
              )}

              {showSkip && (
                <SecondaryButton onPress={handleSkipForNow} fullWidth>
                  Skip for Now
                </SecondaryButton>
              )}
            </View>
          </View>

          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or</Text>
            <View style={styles.dividerLine} />
          </View>

          <TouchableOpacity style={styles.backLink} onPress={handleBack} disabled={isLaunching || isLoadingStatus}>
            <Text style={styles.backLinkText}>Go Back</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>

      <VerificationFormModal
        visible={showVerificationForm}
        accessToken={accessToken}
        formUrl={formUrl}
        onComplete={handleFormComplete}
        onClose={closeFormModal}
      />
    </GradientBackground>
  );
}
