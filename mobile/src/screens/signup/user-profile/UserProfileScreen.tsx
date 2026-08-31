import { View, Text, TextInput, ScrollView, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { GradientBackground } from '../../../components/GradientBackground';
import { PrimaryButton } from '../../../components/buttons';
import { ScreenHeader } from '../../../components/header';
import { DatePickerField } from '../../../components/date-picker';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import type { RootStackParamList } from '../../../navigation/AppNavigator';
import { useUserProfile } from './useUserProfile';
import { UserIcon, WarningCircleIcon, HouseIcon, PhoneIcon } from 'phosphor-react-native';
import { CountrySelector } from './components/CountrySelector';
import { layout } from '../../../styles';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { parseDateString, formatDateToString } from '@ledova/shared-utils';
import { useRole } from '../../../hooks/useRole';

export function UserProfileScreen() {
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
    },
    loadingText: {
      marginTop: theme.spacing.md,
      fontSize: theme.fontSize.base,
      color: theme.colors.text.muted,
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
      marginBottom: theme.spacing.xs,
    },
    helperText: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      marginBottom: theme.spacing.sm,
    },
    inputWrapper: {
      position: 'relative',
    },
    phoneInputWrapper: {
      flexDirection: 'row',
      alignItems: 'stretch',
      position: 'relative',
    },
    inputIcon: {
      position: 'absolute',
      left: theme.spacing.md,
      top: 14,
      zIndex: 1,
    },
    inputIconTop: {
      top: theme.spacing.md,
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
    inputWithIcon: {
      paddingLeft: 44,
    },
    phoneInput: {
      flex: 1,
      borderTopLeftRadius: 0,
      borderBottomLeftRadius: 0,
      borderLeftWidth: 0,
      paddingLeft: theme.spacing.sm,
    },
    textArea: {
      height: 96,
      paddingTop: theme.spacing.md,
    },
    inputError: {
      borderColor: theme.colors.status.error.text,
      backgroundColor: theme.colors.error.subtle,
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
    errors,
    generalError,
    isLoading,
    isSubmitting,
    selectedCountry,
    countries,
    setFieldValue,
    handleCountryChange,
    handleSubmit,
    retryLoad,
  } = useUserProfile();

  const { isCompany } = useRole();

  const handleContinue = async () => {
    await handleSubmit(() => {
      navigation.navigate(isCompany ? 'CompanyRegistration' : 'FinancialProfile');
    });
  };

  const handleBack = () => {
    navigation.navigate('IdentityVerification');
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={theme.colors.interactive.active} />
          <Text style={styles.loadingText}>Loading profile data...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (generalError && !form.fullName && !isSubmitting) {
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
            <ScreenHeader
              icon={
                <UserIcon
                  size={theme.icon.sizes.md}
                  color={theme.colors.text.muted}
                  weight={theme.icon.weights.regular}
                />
              }
              title="Personal Details"
            />

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

              <View style={styles.fieldContainer}>
                <Text style={styles.label}>Full Name</Text>
                <View style={styles.inputWrapper}>
                  <View style={styles.inputIcon}>
                    <UserIcon
                      size={theme.icon.sizes.md}
                      color={theme.colors.text.subtle}
                      weight={theme.icon.weights.regular}
                    />
                  </View>
                  <TextInput
                    style={[styles.input, styles.inputWithIcon, errors.fullName ? styles.inputError : null]}
                    placeholder="John Doe"
                    placeholderTextColor={theme.colors.text.muted}
                    value={form.fullName}
                    onChangeText={(text) => setFieldValue('fullName', text)}
                    editable={!isSubmitting}
                  />
                </View>
                {errors.fullName && <Text style={styles.fieldError}>{errors.fullName.join(' ')}</Text>}
              </View>

              <View style={styles.fieldContainer}>
                <DatePickerField
                  label="Date of Birth"
                  value={parseDateString(form.dateOfBirth)}
                  onChange={(date) => setFieldValue('dateOfBirth', formatDateToString(date))}
                  placeholder="DD/MM/YYYY"
                  maximumDate={new Date()}
                  minimumDate={new Date(1900, 0, 1)}
                />
                {errors.dateOfBirth && <Text style={styles.fieldError}>{errors.dateOfBirth.join(' ')}</Text>}
              </View>

              <View style={styles.fieldContainer}>
                <Text style={styles.label}>Phone Number</Text>
                <View style={styles.phoneInputWrapper}>
                  <View style={styles.inputIcon}>
                    <PhoneIcon
                      size={theme.icon.sizes.md}
                      color={theme.colors.text.subtle}
                      weight={theme.icon.weights.regular}
                    />
                  </View>
                  <CountrySelector
                    countries={countries}
                    selectedCountry={selectedCountry}
                    onCountryChange={handleCountryChange}
                    disabled={isSubmitting}
                  />
                  <TextInput
                    style={[styles.input, styles.phoneInput, errors.phoneNumber ? styles.inputError : null]}
                    placeholder="416 004 021"
                    placeholderTextColor={theme.colors.text.muted}
                    value={form.phoneNumber}
                    onChangeText={(text) => setFieldValue('phoneNumber', text)}
                    keyboardType="phone-pad"
                    editable={!isSubmitting}
                  />
                </View>
                {errors.phoneNumber && <Text style={styles.fieldError}>{errors.phoneNumber.join(' ')}</Text>}
              </View>

              <View style={styles.fieldContainer}>
                <Text style={styles.label}>Residential Address</Text>
                <Text style={styles.helperText}>Include street number, city, state and postcode</Text>
                <View style={styles.inputWrapper}>
                  <View style={[styles.inputIcon, styles.inputIconTop]}>
                    <HouseIcon
                      size={theme.icon.sizes.md}
                      color={theme.colors.text.subtle}
                      weight={theme.icon.weights.regular}
                    />
                  </View>
                  <TextInput
                    style={[
                      styles.input,
                      styles.inputWithIcon,
                      styles.textArea,
                      errors.residentialAddress ? styles.inputError : null,
                    ]}
                    placeholder="123 Main Street&#10;Sydney NSW 2000"
                    placeholderTextColor={theme.colors.text.muted}
                    value={form.residentialAddress}
                    onChangeText={(text) => setFieldValue('residentialAddress', text)}
                    multiline
                    numberOfLines={3}
                    textAlignVertical="top"
                    editable={!isSubmitting}
                  />
                </View>
                {errors.residentialAddress && (
                  <Text style={styles.fieldError}>{errors.residentialAddress.join(' ')}</Text>
                )}
              </View>

              <PrimaryButton onPress={handleContinue} loading={isSubmitting} fullWidth style={styles.continueButton}>
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
