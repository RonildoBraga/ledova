import { View, Text, TextInput, ScrollView, KeyboardAvoidingView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { GradientBackground } from '../../../components/GradientBackground';
import { PrimaryButton } from '../../../components/buttons';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import type { RootStackParamList } from '../../../navigation/AppNavigator';
import { useEmailConfirmation } from './useEmailConfirmation';
import { formatVerificationToken, EMAIL_CONFIRMATION_VALIDATION } from '@ledova/shared';
import { EnvelopeOpenIcon, CheckCircleIcon, WarningCircleIcon } from 'phosphor-react-native';
import { layout } from '../../../styles';
import { useAppTheme, useThemedStyles } from '../../../contexts';

export function EmailConfirmationScreen() {
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
    },
    formContainer: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      padding: theme.spacing.lg,
    },
    successContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: `${theme.colors.status.success.icon}20`,
      borderWidth: 1,
      borderColor: theme.colors.badge.success.background,
      borderRadius: theme.borderRadius.md,
      padding: theme.spacing.md,
      marginBottom: theme.spacing.lg,
    },
    successText: {
      color: theme.colors.status.success.icon,
      fontSize: theme.fontSize.sm,
      marginLeft: theme.spacing.sm,
      flex: 1,
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
    codeInput: {
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.strong,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.md,
      height: 56,
      fontSize: theme.fontSize.xxl,
      color: theme.colors.text.primary,
      textAlign: 'center',
      letterSpacing: 8,
      fontWeight: theme.fontWeight.semibold,
    },
    fieldError: {
      color: theme.colors.status.error.icon,
      fontSize: theme.fontSize.xs,
      marginTop: theme.spacing.xs,
    },
    verifyButton: {
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
    actionsSection: {
      alignItems: 'center',
      gap: theme.spacing.md,
    },
    actionsText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
    actionLink: {
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.semibold,
    },
    actionLinkDisabled: {
      opacity: 0.5,
    },
  }));
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();

  const {
    verificationCode,
    errors,
    generalError,
    successMessage,
    isLoading,
    isResending,
    setVerificationCode,
    handleVerify,
    handleResend,
  } = useEmailConfirmation();

  const handleConfirm = async () => {
    await handleVerify(() => {
      navigation.navigate('AccountType');
    });
  };

  return (
    <GradientBackground>
      <SafeAreaView style={styles.container}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.keyboardView}>
          <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
            <View style={styles.header}>
              <View style={styles.iconContainer}>
                <EnvelopeOpenIcon
                  size={theme.icon.sizes.md}
                  color={theme.colors.text.muted}
                  weight={theme.icon.weights.regular}
                />
              </View>
              <Text style={styles.title}>Verify Your Email</Text>
            </View>

            <View style={styles.formContainer}>
              {successMessage && (
                <View style={styles.successContainer}>
                  <CheckCircleIcon
                    size={theme.icon.sizes.md}
                    color={theme.colors.status.success.icon}
                    weight={theme.icon.weights.regular}
                  />
                  <Text style={styles.successText}>{successMessage}</Text>
                </View>
              )}

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
                <Text style={styles.label}>Verification Code</Text>
                <TextInput
                  style={styles.codeInput}
                  placeholder="000000"
                  placeholderTextColor={theme.colors.form.placeholder}
                  value={verificationCode}
                  onChangeText={(text) => {
                    const cleaned = formatVerificationToken(text).slice(0, EMAIL_CONFIRMATION_VALIDATION.TOKEN_LENGTH);
                    setVerificationCode(cleaned);
                  }}
                  keyboardType="number-pad"
                  maxLength={6}
                  autoFocus
                  editable={!isLoading}
                />
                {errors.token && <Text style={styles.fieldError}>{errors.token.join(' ')}</Text>}
              </View>

              <PrimaryButton
                onPress={handleConfirm}
                loading={isLoading}
                disabled={verificationCode.length !== EMAIL_CONFIRMATION_VALIDATION.TOKEN_LENGTH}
                fullWidth
                style={styles.verifyButton}
              >
                Verify
              </PrimaryButton>
            </View>

            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            <View style={styles.actionsSection}>
              <Text style={styles.actionsText}>
                Didn&apos;t receive the code?{' '}
                <Text
                  style={[styles.actionLink, (isResending || isLoading) && styles.actionLinkDisabled]}
                  onPress={() => !isResending && !isLoading && handleResend()}
                >
                  {isResending ? 'Sending...' : 'Resend'}
                </Text>
              </Text>
              <Text style={styles.actionsText}>
                <Text style={styles.actionLink} onPress={() => !isLoading && navigation.navigate('SignUp')}>
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
