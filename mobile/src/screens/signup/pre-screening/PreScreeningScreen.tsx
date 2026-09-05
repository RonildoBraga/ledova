import {
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { GradientBackground } from '../../../components/GradientBackground';
import { PrimaryButton } from '../../../components/buttons';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import type { RootStackParamList } from '../../../navigation/AppNavigator';
import { usePreScreening } from './usePreScreening';
import { ShieldCheckIcon, WarningCircleIcon, CheckCircleIcon } from 'phosphor-react-native';
import { layout } from '../../../styles';
import { useAppTheme, useThemedStyles } from '../../../contexts';

export function PreScreeningScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    keyboardView: {
      flex: 1,
    },
    scrollContent: {
      flexGrow: 1,
      justifyContent: 'center',
      paddingHorizontal: theme.spacing.sm,
      paddingTop: theme.spacing.xs,
      paddingBottom: layout.screenBottomPadding,
    },
    loadingContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      gap: theme.spacing.md,
    },
    loadingText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
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
      marginBottom: theme.spacing.sm,
    },
    subtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
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
      color: theme.colors.form.error,
      fontSize: theme.fontSize.sm,
      marginLeft: theme.spacing.sm,
      flex: 1,
    },
    checkboxContainer: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      marginBottom: theme.spacing.lg,
    },
    checkbox: {
      width: 24,
      height: 24,
      borderRadius: theme.borderRadius.sm,
      borderWidth: 2,
      borderColor: theme.colors.border.default,
      backgroundColor: theme.colors.surface.tertiary,
      justifyContent: 'center',
      alignItems: 'center',
      marginTop: 2,
    },
    checkboxChecked: {
      backgroundColor: theme.colors.interactive.defaultSubtle,
      borderColor: theme.colors.interactive.defaultSubtle,
    },
    checkboxTextContainer: {
      flex: 1,
      marginLeft: theme.spacing.md,
    },
    checkboxLabel: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.xs,
    },
    checkboxHelper: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
    },
    continueButton: {
      marginTop: theme.spacing.md,
      shadowColor: theme.colors.interactive.active,
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.4,
      shadowRadius: 8,
      elevation: 4,
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
    backSection: {
      alignItems: 'center',
    },
    backText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
    backLink: {
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.semibold,
    },
    errorStateContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      paddingHorizontal: theme.spacing.xl,
    },
    errorStateTitle: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginTop: theme.spacing.md,
      marginBottom: theme.spacing.sm,
    },
    errorStateMessage: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.muted,
      textAlign: 'center',
      marginBottom: theme.spacing.xl,
    },
  }));
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();
  const {
    form,
    acknowledgedWholesaleOnly,
    toggleWholesaleOnly,
    generalError,
    isLoading,
    isSubmitting,
    isFormValid,
    setFieldValue,
    handleSubmit,
    retryLoad,
  } = usePreScreening();

  const handleContinue = async () => {
    await handleSubmit(() => {
      navigation.navigate('IdentityVerification');
    });
  };

  const handleBack = () => {
    navigation.navigate('EmailConfirmation');
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.interactive.active} />
          <Text style={styles.loadingText}>Loading...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (generalError && !isSubmitting) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.errorStateContainer}>
          <WarningCircleIcon
            size={theme.icon.sizes.md}
            color={theme.colors.status.error.text}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.errorStateTitle}>Unable to Load</Text>
          <Text style={styles.errorStateMessage}>{generalError}</Text>
          <PrimaryButton onPress={retryLoad}>Try Again</PrimaryButton>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <GradientBackground>
      <SafeAreaView style={styles.container}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.keyboardView}>
          <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
            <View style={styles.header}>
              <View style={styles.iconContainer}>
                <ShieldCheckIcon
                  size={theme.icon.sizes.md}
                  color={theme.colors.text.muted}
                  weight={theme.icon.weights.regular}
                />
              </View>
              <Text style={styles.title}>Eligibility Check</Text>
              <Text style={styles.subtitle}>
                Before we continue, please confirm the following requirements to comply with Australian regulations.
              </Text>
            </View>

            <View style={styles.formContainer}>
              {generalError && (
                <View style={styles.errorContainer}>
                  <WarningCircleIcon
                    size={theme.icon.sizes.md}
                    color={theme.colors.status.error.icon}
                    weight={theme.icon.weights.regular}
                  />
                  <Text style={styles.errorText}>{generalError}</Text>
                </View>
              )}

              <TouchableOpacity
                style={styles.checkboxContainer}
                onPress={() => setFieldValue('confirmedOver18', !form.confirmedOver18)}
                disabled={isSubmitting}
                activeOpacity={0.7}
              >
                <View style={[styles.checkbox, form.confirmedOver18 && styles.checkboxChecked]}>
                  {form.confirmedOver18 && (
                    <CheckCircleIcon
                      size={theme.icon.sizes.md}
                      color={theme.colors.utility.white}
                      weight={theme.icon.weights.regular}
                    />
                  )}
                </View>
                <View style={styles.checkboxTextContainer}>
                  <Text style={styles.checkboxLabel}>I am 18 years or older</Text>
                  <Text style={styles.checkboxHelper}>You must be at least 18 to use our platform</Text>
                </View>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.checkboxContainer}
                onPress={() => setFieldValue('confirmedAustralianResident', !form.confirmedAustralianResident)}
                disabled={isSubmitting}
                activeOpacity={0.7}
              >
                <View style={[styles.checkbox, form.confirmedAustralianResident && styles.checkboxChecked]}>
                  {form.confirmedAustralianResident && (
                    <CheckCircleIcon
                      size={theme.icon.sizes.md}
                      color={theme.colors.utility.white}
                      weight={theme.icon.weights.regular}
                    />
                  )}
                </View>
                <View style={styles.checkboxTextContainer}>
                  <Text style={styles.checkboxLabel}>I am currently an Australian resident</Text>
                  <Text style={styles.checkboxHelper}>
                    Our services are currently only available to Australian residents
                  </Text>
                </View>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.checkboxContainer}
                onPress={() => setFieldValue('confirmedIndividualAccount', !form.confirmedIndividualAccount)}
                disabled={isSubmitting}
                activeOpacity={0.7}
              >
                <View style={[styles.checkbox, form.confirmedIndividualAccount && styles.checkboxChecked]}>
                  {form.confirmedIndividualAccount && (
                    <CheckCircleIcon
                      size={theme.icon.sizes.md}
                      color={theme.colors.utility.white}
                      weight={theme.icon.weights.regular}
                    />
                  )}
                </View>
                <View style={styles.checkboxTextContainer}>
                  <Text style={styles.checkboxLabel}>I am acting on my own behalf</Text>
                  <Text style={styles.checkboxHelper}>Not for a business, trust, or on behalf of someone else</Text>
                </View>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.checkboxContainer}
                onPress={toggleWholesaleOnly}
                disabled={isSubmitting}
                activeOpacity={0.7}
              >
                <View style={[styles.checkbox, acknowledgedWholesaleOnly && styles.checkboxChecked]}>
                  {acknowledgedWholesaleOnly && (
                    <CheckCircleIcon
                      size={theme.icon.sizes.md}
                      color={theme.colors.utility.white}
                      weight={theme.icon.weights.regular}
                    />
                  )}
                </View>
                <View style={styles.checkboxTextContainer}>
                  <Text style={styles.checkboxLabel}>I understand share offerings here are wholesale only</Text>
                  <Text style={styles.checkboxHelper}>
                    Offers are made without a disclosure document to wholesale and sophisticated investors. You will
                    need to evidence that status before you can subscribe.
                  </Text>
                </View>
              </TouchableOpacity>

              <PrimaryButton
                onPress={handleContinue}
                loading={isSubmitting}
                disabled={!isFormValid}
                fullWidth
                style={styles.continueButton}
              >
                Continue
              </PrimaryButton>
            </View>

            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            <View style={styles.backSection}>
              <Text style={styles.backText}>
                <Text style={styles.backLink} onPress={() => !isSubmitting && handleBack()}>
                  Go Back
                </Text>
              </Text>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </GradientBackground>
  );
}
