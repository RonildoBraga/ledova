import { useCallback, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation, NavigationProp, useFocusEffect } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { GradientBackground } from '../../components/GradientBackground';
import { PrimaryButton } from '../../components/buttons';
import { useSignIn } from './useSignIn';
import { useAppLock } from '../../contexts';
import {
  LockIcon,
  EnvelopeSimpleIcon,
  EyeIcon,
  EyeSlashIcon,
  WarningCircleIcon,
  ScanSmileyIcon,
  KeyIcon,
} from 'phosphor-react-native';
import { layout } from '../../styles';
import { useAppTheme, useThemedStyles } from '../../contexts';
import type { RootStackParamList } from '../../navigation/AppNavigator';

export function SignInScreen() {
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
    labelRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: theme.spacing.sm,
    },
    label: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.body,
      marginBottom: theme.spacing.sm,
    },
    forgotPassword: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.interactive.active,
    },
    inputWrapper: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.strong,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.md,
      height: 48,
    },
    inputIcon: {
      marginRight: theme.spacing.sm,
    },
    input: {
      flex: 1,
      color: theme.colors.text.primary,
      fontSize: theme.fontSize.base,
    },
    passwordInput: {
      paddingRight: 40,
    },
    eyeButton: {
      position: 'absolute',
      right: theme.spacing.md,
      height: 48,
      justifyContent: 'center',
    },
    fieldError: {
      color: theme.colors.status.error.icon,
      fontSize: theme.fontSize.xs,
      marginTop: theme.spacing.xs,
    },
    signInButton: {
      marginTop: theme.spacing.md,
      shadowColor: theme.colors.interactive.active,
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.4,
      shadowRadius: 8,
      elevation: 4,
    },
    buttonContent: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: theme.spacing.sm,
    },
    signInButtonText: {
      color: theme.colors.utility.white,
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
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
    signUpSection: {
      alignItems: 'center',
    },
    signUpText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.subtle,
      textAlign: 'center',
    },
    getStartedLink: {
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.semibold,
    },
  }));
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();
  const {
    biometricsAvailable,
    hasBiometricLogin,
    biometricType,
    biometricLoginEnabled,
    enableBiometricLogin,
    readBiometricRefreshToken,
    reloadBiometricLogin,
  } = useAppLock();
  const [biometricLoading, setBiometricLoading] = useState(false);

  // Clear all cached query data when navigating to signin screen
  // This prevents data from incomplete signup flows from bleeding into new sessions.
  // Also re-read the biometric sign-in state: sign-out deletes the gated refresh token.
  useFocusEffect(
    useCallback(() => {
      queryClient.clear();
      reloadBiometricLogin();
    }, [queryClient, reloadBiometricLogin]),
  );

  const {
    form,
    errors,
    generalError,
    isLoading,
    showPassword,
    setFieldValue,
    togglePassword,
    handleSubmit,
    loginWithRefreshToken,
    setGeneralError,
  } = useSignIn();

  const navigateToMainApp = useCallback(() => {
    navigation.reset({
      index: 0,
      routes: [{ name: 'MainApp' }],
    });
  }, [navigation]);

  const handleSignIn = async () => {
    // Smart login: if Face ID enabled AND no credentials entered, use biometric login
    const hasCredentialsEntered = form.email.trim() || form.password;
    if (showBiometricLogin && !hasCredentialsEntered) {
      await handleBiometricLogin();
      return;
    }

    // Otherwise, use password login
    await handleSubmit(async () => {
      // If biometrics are available and biometric sign in is not enabled yet, offer it
      if (biometricsAvailable && !biometricLoginEnabled) {
        Alert.alert(
          `Enable ${biometricType} Sign In?`,
          `Would you like to use ${biometricType} to sign in next time?`,
          [
            {
              text: 'Not Now',
              style: 'cancel',
              onPress: navigateToMainApp,
            },
            {
              text: 'Enable',
              onPress: async () => {
                // Stores a biometric-gated copy of the session's refresh token; the password is never stored.
                // A failure is silent: the user can enable it later in settings.
                await enableBiometricLogin();
                navigateToMainApp();
              },
            },
          ],
        );
      } else {
        navigateToMainApp();
      }
    });
  };

  // Biometric sign in: the OS prompt unlocks the gated refresh token, which is exchanged for a new session
  const handleBiometricLogin = async () => {
    setBiometricLoading(true);
    try {
      const result = await readBiometricRefreshToken();
      if (result.token) {
        const signedIn = await loginWithRefreshToken(result.token, navigateToMainApp);
        if (!signedIn) {
          // Revoked by a sign-out or expired: the gated copy is gone and the password form takes over
          await reloadBiometricLogin();
        }
      } else if (result.missing) {
        setGeneralError(`${biometricType} sign in needs to be set up again. Please sign in with your password.`);
      }
    } finally {
      setBiometricLoading(false);
    }
  };

  // Show biometric login option if available and a gated refresh token is on the device
  const showBiometricLogin = biometricsAvailable && hasBiometricLogin;

  return (
    <GradientBackground>
      <SafeAreaView style={styles.container}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.keyboardView}>
          <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
            {/* Header */}
            <View style={styles.header}>
              <View style={styles.iconContainer}>
                <LockIcon
                  size={theme.icon.sizes.md}
                  color={theme.colors.text.muted}
                  weight={theme.icon.weights.regular}
                />
              </View>
              <Text style={styles.title}>Welcome Back</Text>
            </View>

            {/* Form Container */}
            <View style={styles.formContainer}>
              {/* General Error */}
              {generalError && (
                <View style={styles.errorContainer}>
                  <WarningCircleIcon
                    size={theme.icon.sizes.md}
                    color={theme.colors.form.error}
                    weight={theme.icon.weights.regular}
                  />
                  <Text style={styles.errorText}>{generalError}</Text>
                </View>
              )}

              {/* Email Field */}
              <View style={styles.fieldContainer}>
                <Text style={styles.label}>Email</Text>
                <View style={styles.inputWrapper}>
                  <EnvelopeSimpleIcon
                    size={theme.icon.sizes.md}
                    color={theme.colors.text.subtle}
                    style={styles.inputIcon}
                  />
                  <TextInput
                    style={styles.input}
                    placeholder="your@email.com"
                    placeholderTextColor={theme.colors.form.placeholder}
                    value={form.email}
                    onChangeText={(text) => setFieldValue('email', text)}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    autoCorrect={false}
                    editable={!isLoading}
                  />
                </View>
                {errors.email && !generalError && <Text style={styles.fieldError}>{errors.email.join(' ')}</Text>}
              </View>

              {/* Password Field */}
              <View style={styles.fieldContainer}>
                <View style={styles.labelRow}>
                  <Text style={styles.label}>Password</Text>
                  <TouchableOpacity disabled={isLoading}>
                    <Text style={styles.forgotPassword}>Forgot?</Text>
                  </TouchableOpacity>
                </View>
                <View style={styles.inputWrapper}>
                  <LockIcon size={theme.icon.sizes.md} color={theme.colors.text.subtle} style={styles.inputIcon} />
                  <TextInput
                    style={[styles.input, styles.passwordInput]}
                    placeholder="••••••••"
                    placeholderTextColor={theme.colors.form.placeholder}
                    value={form.password}
                    onChangeText={(text) => setFieldValue('password', text)}
                    secureTextEntry={!showPassword}
                    autoCapitalize="none"
                    editable={!isLoading}
                  />
                  <TouchableOpacity onPress={togglePassword} style={styles.eyeButton} disabled={isLoading}>
                    {showPassword ? (
                      <EyeSlashIcon
                        size={theme.icon.sizes.md}
                        color={theme.colors.text.subtle}
                        weight={theme.icon.weights.regular}
                      />
                    ) : (
                      <EyeIcon
                        size={theme.icon.sizes.md}
                        color={theme.colors.text.subtle}
                        weight={theme.icon.weights.regular}
                      />
                    )}
                  </TouchableOpacity>
                </View>
                {errors.password && !generalError && <Text style={styles.fieldError}>{errors.password.join(' ')}</Text>}
              </View>

              {/* Sign In Button - Smart: uses Face ID if enabled and no credentials entered */}
              <PrimaryButton
                onPress={handleSignIn}
                loading={isLoading || biometricLoading}
                fullWidth
                style={styles.signInButton}
              >
                <View style={styles.buttonContent}>
                  {showBiometricLogin ? (
                    <ScanSmileyIcon size={22} color={theme.colors.utility.white} weight="regular" />
                  ) : (
                    <KeyIcon size={22} color={theme.colors.utility.white} weight="regular" />
                  )}
                  <Text style={styles.signInButtonText}>Sign In</Text>
                </View>
              </PrimaryButton>
            </View>

            {/* Divider */}
            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            {/* Get Started Section */}
            <View style={styles.signUpSection}>
              <Text style={styles.signUpText}>
                Don&apos;t have an account?{' '}
                <Text style={styles.getStartedLink} onPress={() => !isLoading && navigation.navigate('SignUp')}>
                  Get Started
                </Text>
              </Text>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </GradientBackground>
  );
}
