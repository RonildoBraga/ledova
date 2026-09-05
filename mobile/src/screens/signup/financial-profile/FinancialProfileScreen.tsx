import {
  View,
  Text,
  TextInput,
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
import { useFinancialProfile } from './useFinancialProfile';
import { WarningCircleIcon, ChartBarIcon } from 'phosphor-react-native';
import { CheckIcon } from 'phosphor-react-native';
import { layout } from '../../../styles';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { SOURCE_OF_FUNDS_OPTIONS, INTENDED_USE_OPTIONS } from '@ledova/shared';

/**
 * Financial Profile Screen - AML/CTF Compliance
 *
 * Collects source of funds, occupation, and intended use as required by
 * Ledova AML/CTF Program (Part B, Section 16.1, Step 4).
 */
export function FinancialProfileScreen() {
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
      backgroundColor: theme.colors.error.default + '1A',
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
    fieldContainer: {
      marginBottom: theme.spacing.lg,
    },
    label: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.body,
      marginBottom: theme.spacing.sm,
    },
    labelHint: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      fontWeight: theme.fontWeight.normal,
      marginBottom: theme.spacing.md,
    },
    radioGroup: {
      gap: theme.spacing.sm,
    },
    radioItem: {
      flexDirection: 'row',
      alignItems: 'center',
      marginBottom: theme.spacing.sm,
    },
    radio: {
      width: 16,
      height: 16,
      borderRadius: theme.borderRadius.md,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      backgroundColor: theme.colors.surface.tertiary,
      marginRight: theme.spacing.md,
      justifyContent: 'center',
      alignItems: 'center',
    },
    radioSelected: {
      width: 8,
      height: 8,
      borderRadius: theme.borderRadius.sm,
      backgroundColor: theme.colors.interactive.default,
    },
    radioLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.body,
    },
    checkboxGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: theme.spacing.sm,
    },
    checkboxItem: {
      flexDirection: 'row',
      alignItems: 'center',
      width: '48%',
      marginBottom: theme.spacing.sm,
    },
    checkbox: {
      width: 16,
      height: 16,
      borderRadius: theme.borderRadius.sm,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      backgroundColor: theme.colors.surface.tertiary,
      marginRight: theme.spacing.sm,
      justifyContent: 'center',
      alignItems: 'center',
    },
    checkboxChecked: {
      backgroundColor: theme.colors.interactive.default,
      borderColor: theme.colors.interactive.default,
    },
    checkboxLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.body,
      flex: 1,
    },
    input: {
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.md,
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
      height: 48,
    },
    inputError: {
      borderColor: theme.colors.status.error.text,
    },
    fieldError: {
      color: theme.colors.status.error.icon,
      fontSize: theme.fontSize.xs,
      marginTop: theme.spacing.xs,
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
  }));
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();
  const {
    form,
    errors,
    generalError,
    isLoading,
    isSubmitting,
    userProfileId,
    setFieldValue,
    toggleSourceOfFunds,
    handleSubmit,
    retryLoad,
  } = useFinancialProfile();

  const handleContinue = async () => {
    await handleSubmit(() => {
      navigation.navigate('Review');
    });
  };

  const handleBack = () => {
    navigation.navigate('UserProfile');
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.interactive.active} />
          <Text style={styles.loadingText}>Loading financial profile...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!userProfileId && !isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.errorStateContainer}>
          <WarningCircleIcon
            size={theme.icon.sizes.md}
            color={theme.colors.status.error.text}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.errorStateTitle}>Profile Not Found</Text>
          <Text style={styles.errorStateMessage}>
            Please complete your user profile before setting your financial profile.
          </Text>
          <PrimaryButton onPress={() => navigation.navigate('UserProfile')}>Go to Profile</PrimaryButton>
        </View>
      </SafeAreaView>
    );
  }

  if (generalError && !form.occupation && !isSubmitting && !isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.errorStateContainer}>
          <WarningCircleIcon
            size={theme.icon.sizes.md}
            color={theme.colors.status.error.text}
            weight={theme.icon.weights.regular}
          />
          <Text style={styles.errorStateTitle}>Unable to Load Profile</Text>
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
            {/* Header */}
            <View style={styles.header}>
              <View style={styles.iconContainer}>
                <ChartBarIcon
                  size={theme.icon.sizes.md}
                  color={theme.colors.text.muted}
                  weight={theme.icon.weights.regular}
                />
              </View>
              <Text style={styles.title}>Financial Profile</Text>
              <Text style={styles.subtitle}>AML/CTF compliance information</Text>
            </View>

            {/* Form Container */}
            <View style={styles.formContainer}>
              {/* General Error */}
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

              {/* Source of Funds - AML/CTF Required */}
              <View style={styles.fieldContainer}>
                <Text style={styles.label}>What is your primary source of funds?</Text>
                <Text style={styles.labelHint}>select all that apply</Text>
                <View style={styles.checkboxGrid}>
                  {SOURCE_OF_FUNDS_OPTIONS.map((option) => {
                    const isChecked = form.sourceOfFunds.includes(option.value);
                    return (
                      <TouchableOpacity
                        key={option.value}
                        style={styles.checkboxItem}
                        onPress={() => toggleSourceOfFunds(option.value)}
                        disabled={isSubmitting}
                      >
                        <View style={[styles.checkbox, isChecked && styles.checkboxChecked]}>
                          {isChecked && (
                            <CheckIcon
                              size={theme.icon.sizes.md}
                              color={theme.colors.utility.white}
                              weight={theme.icon.weights.regular}
                            />
                          )}
                        </View>
                        <Text style={styles.checkboxLabel}>{option.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
                {errors.sourceOfFunds && <Text style={styles.fieldError}>{errors.sourceOfFunds.join(' ')}</Text>}
              </View>

              {/* Source of Funds - Other Specification */}
              {form.sourceOfFunds.includes('other') && (
                <View style={styles.fieldContainer}>
                  <Text style={styles.label}>Please specify your source of funds</Text>
                  <TextInput
                    style={[styles.input, errors.sourceOfFundsOtherText ? styles.inputError : null]}
                    placeholder="Enter details"
                    placeholderTextColor={theme.colors.form.placeholder}
                    value={form.sourceOfFundsOtherText || ''}
                    onChangeText={(value) => setFieldValue('sourceOfFundsOtherText', value)}
                    editable={!isSubmitting}
                  />
                  {errors.sourceOfFundsOtherText && (
                    <Text style={styles.fieldError}>{errors.sourceOfFundsOtherText.join(' ')}</Text>
                  )}
                </View>
              )}

              {/* Intended Use - AML/CTF Required */}
              <View style={styles.fieldContainer}>
                <Text style={styles.label}>What is your intended use of the platform?</Text>
                <View style={styles.radioGroup}>
                  {INTENDED_USE_OPTIONS.map((option) => (
                    <TouchableOpacity
                      key={option.value}
                      style={styles.radioItem}
                      onPress={() => setFieldValue('intendedUse', option.value)}
                      disabled={isSubmitting}
                    >
                      <View style={styles.radio}>
                        {form.intendedUse === option.value && <View style={styles.radioSelected} />}
                      </View>
                      <Text style={styles.radioLabel}>{option.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                {errors.intendedUse && <Text style={styles.fieldError}>{errors.intendedUse.join(' ')}</Text>}
              </View>

              {/* Intended Use - Other Specification */}
              {form.intendedUse === 'other' && (
                <View style={styles.fieldContainer}>
                  <Text style={styles.label}>Please specify your intended use</Text>
                  <TextInput
                    style={[styles.input, errors.intendedUseOtherText ? styles.inputError : null]}
                    placeholder="Enter details"
                    placeholderTextColor={theme.colors.form.placeholder}
                    value={form.intendedUseOtherText || ''}
                    onChangeText={(value) => setFieldValue('intendedUseOtherText', value)}
                    editable={!isSubmitting}
                  />
                  {errors.intendedUseOtherText && (
                    <Text style={styles.fieldError}>{errors.intendedUseOtherText.join(' ')}</Text>
                  )}
                </View>
              )}

              {/* Occupation - AML/CTF Required (moved to bottom) */}
              <View style={styles.fieldContainer}>
                <Text style={styles.label}>What is your occupation?</Text>
                <TextInput
                  style={[styles.input, errors.occupation ? styles.inputError : null]}
                  placeholder="Enter your occupation"
                  placeholderTextColor={theme.colors.form.placeholder}
                  value={form.occupation || ''}
                  onChangeText={(value) => setFieldValue('occupation', value)}
                  editable={!isSubmitting}
                />
                {errors.occupation && <Text style={styles.fieldError}>{errors.occupation.join(' ')}</Text>}
              </View>

              {/* Continue Button - Primary Action */}
              <PrimaryButton onPress={handleContinue} loading={isSubmitting} fullWidth style={styles.continueButton}>
                Continue
              </PrimaryButton>
            </View>

            {/* Divider */}
            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            {/* Go Back Section */}
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
