import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Linking, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { GradientBackground } from '../../../components/GradientBackground';
import { PrimaryButton } from '../../../components/buttons';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import type { RootStackParamList } from '../../../navigation/AppNavigator';
import { ClipboardIcon } from 'phosphor-react-native';
import { layout } from '../../../styles';
import { useAppTheme, useThemedStyles } from '../../../contexts';
import { useReview } from './useReview';
import {
  formatPhoneNumber,
  getAddressDisplayLines,
  parseAddress,
  formatSourceOfFunds,
  formatIntendedUse,
} from '@ledova/shared-utils';
import { EXTERNAL_URLS } from '@ledova/shared-constants';

export function ReviewScreen() {
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
      gap: theme.spacing.md,
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
    errorContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      paddingHorizontal: theme.spacing.xl,
    },
    errorTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.form.error,
      marginBottom: theme.spacing.sm,
    },
    errorMessage: {
      fontSize: theme.fontSize.base,
      color: theme.colors.status.error.icon,
      textAlign: 'center',
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
    },
    subtitle: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
      paddingHorizontal: theme.spacing.md,
      lineHeight: theme.lineHeight.normal * theme.fontSize.sm,
    },
    card: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
    },
    cardHeader: {
      paddingVertical: theme.spacing.md,
      paddingHorizontal: theme.spacing.lg,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    cardContent: {
      padding: theme.spacing.lg,
    },
    sectionTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    infoList: {
      gap: theme.spacing.md,
    },
    infoRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      paddingVertical: theme.spacing.sm,
      paddingHorizontal: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    infoRowVertical: {
      gap: theme.spacing.sm,
    },
    infoLabel: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      fontWeight: theme.fontWeight.medium,
    },
    infoValue: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
      fontWeight: theme.fontWeight.medium,
      textAlign: 'right',
      flex: 1,
    },
    infoValueVertical: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
      fontWeight: theme.fontWeight.medium,
      textAlign: 'left',
    },
    errorText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.icon,
    },
    termsText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.body,
      lineHeight: theme.lineHeight.normal * theme.fontSize.sm,
    },
    linkText: {
      color: theme.colors.interactive.active,
      textDecorationLine: 'underline',
    },
    buttonContainer: {
      paddingHorizontal: theme.spacing.lg,
      paddingBottom: theme.spacing.lg,
    },
    completeButton: {
      shadowColor: theme.colors.interactive.active,
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.4,
      shadowRadius: 8,
      elevation: 4,
    },
    validationText: {
      marginBottom: theme.spacing.md,
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.icon,
      textAlign: 'center',
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
      paddingVertical: theme.spacing.md,
    },
    backLink: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.semibold,
    },
  }));
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();
  const { data, company, isCompany, isLoading, error, completeSignup, isSubmitting, canCompleteSignup } = useReview();

  const handleBack = () => {
    navigation.navigate(isCompany ? 'CompanyRegistration' : 'FinancialProfile');
  };

  const handleOpenTerms = async () => {
    try {
      const supported = await Linking.canOpenURL(EXTERNAL_URLS.TERMS_OF_SERVICE);
      if (supported) {
        await Linking.openURL(EXTERNAL_URLS.TERMS_OF_SERVICE);
      } else {
        Alert.alert('Error', `Unable to open URL: ${EXTERNAL_URLS.TERMS_OF_SERVICE}`);
      }
    } catch {
      Alert.alert('Error', 'Failed to open Terms of Service');
    }
  };

  const handleOpenPrivacyPolicy = async () => {
    try {
      const supported = await Linking.canOpenURL(EXTERNAL_URLS.PRIVACY_POLICY);
      if (supported) {
        await Linking.openURL(EXTERNAL_URLS.PRIVACY_POLICY);
      } else {
        Alert.alert('Error', `Unable to open URL: ${EXTERNAL_URLS.PRIVACY_POLICY}`);
      }
    } catch {
      Alert.alert('Error', 'Failed to open Privacy Policy');
    }
  };

  if (isLoading) {
    return (
      <GradientBackground>
        <SafeAreaView style={styles.container}>
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={theme.colors.interactive.active} />
            <Text style={styles.loadingText}>Loading review data...</Text>
          </View>
        </SafeAreaView>
      </GradientBackground>
    );
  }

  if (error) {
    return (
      <GradientBackground>
        <SafeAreaView style={styles.container}>
          <View style={styles.errorContainer}>
            <Text style={styles.errorTitle}>Error Loading Data</Text>
            <Text style={styles.errorMessage}>{error}</Text>
          </View>
        </SafeAreaView>
      </GradientBackground>
    );
  }

  const { userProfile, financialProfile } = data;

  return (
    <GradientBackground>
      <SafeAreaView style={styles.container}>
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <View style={styles.header}>
            <View style={styles.iconContainer}>
              <ClipboardIcon
                size={theme.icon.sizes.md}
                color={theme.colors.text.muted}
                weight={theme.icon.weights.regular}
              />
            </View>
            <Text style={styles.title}>Review & Confirm</Text>
            <Text style={styles.subtitle}>Please review your information before completing signup</Text>
          </View>

          <View style={styles.card}>
            <View style={styles.cardHeader}>
              <Text style={styles.sectionTitle}>Personal Information</Text>
            </View>
            <View style={styles.cardContent}>
              {userProfile ? (
                <View style={styles.infoList}>
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>Full Name:</Text>
                    <Text style={styles.infoValue}>{userProfile.fullName}</Text>
                  </View>
                  <View style={styles.infoRow}>
                    <Text style={styles.infoLabel}>Phone:</Text>
                    <Text style={styles.infoValue}>{formatPhoneNumber(userProfile.phoneNumber)}</Text>
                  </View>
                  {getAddressDisplayLines(parseAddress(userProfile.residentialAddress)).map((line, index) => (
                    <View key={index} style={styles.infoRow}>
                      <Text style={styles.infoLabel}>{line.label}</Text>
                      <Text style={styles.infoValue}>{line.value}</Text>
                    </View>
                  ))}
                </View>
              ) : (
                <Text style={styles.errorText}>No personal information found.</Text>
              )}
            </View>
          </View>

          {isCompany ? (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.sectionTitle}>Company Information</Text>
              </View>
              <View style={styles.cardContent}>
                {company ? (
                  <View style={styles.infoList}>
                    <View style={styles.infoRow}>
                      <Text style={styles.infoLabel}>Company:</Text>
                      <Text style={styles.infoValue}>{company.name}</Text>
                    </View>
                    {company.tradingName ? (
                      <View style={styles.infoRow}>
                        <Text style={styles.infoLabel}>Trading As:</Text>
                        <Text style={styles.infoValue}>{company.tradingName}</Text>
                      </View>
                    ) : null}
                    <View style={styles.infoRow}>
                      <Text style={styles.infoLabel}>ACN:</Text>
                      <Text style={styles.infoValue}>{company.acn}</Text>
                    </View>
                    {company.abn ? (
                      <View style={styles.infoRow}>
                        <Text style={styles.infoLabel}>ABN:</Text>
                        <Text style={styles.infoValue}>{company.abn}</Text>
                      </View>
                    ) : null}
                  </View>
                ) : (
                  <Text style={styles.errorText}>No company information found.</Text>
                )}
              </View>
            </View>
          ) : (
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Text style={styles.sectionTitle}>Financial Profile</Text>
              </View>
              <View style={styles.cardContent}>
                {financialProfile ? (
                  <View style={styles.infoList}>
                    <View style={styles.infoRow}>
                      <Text style={styles.infoLabel}>Source of Funds:</Text>
                      <Text style={styles.infoValue}>{formatSourceOfFunds(financialProfile.sourceOfFunds)}</Text>
                    </View>
                    {financialProfile.sourceOfFundsOtherText && (
                      <View style={styles.infoRowVertical}>
                        <Text style={styles.infoLabel}>Source of Funds (Other):</Text>
                        <Text style={styles.infoValueVertical}>{financialProfile.sourceOfFundsOtherText}</Text>
                      </View>
                    )}
                    {financialProfile.intendedUse && (
                      <View style={styles.infoRow}>
                        <Text style={styles.infoLabel}>Intended Use:</Text>
                        <Text style={styles.infoValue}>{formatIntendedUse(financialProfile.intendedUse)}</Text>
                      </View>
                    )}
                    {financialProfile.intendedUseOtherText && (
                      <View style={styles.infoRowVertical}>
                        <Text style={styles.infoLabel}>Intended Use (Other):</Text>
                        <Text style={styles.infoValueVertical}>{financialProfile.intendedUseOtherText}</Text>
                      </View>
                    )}
                    {financialProfile.occupation && (
                      <View style={styles.infoRow}>
                        <Text style={styles.infoLabel}>Occupation:</Text>
                        <Text style={styles.infoValue}>{financialProfile.occupation}</Text>
                      </View>
                    )}
                  </View>
                ) : (
                  <Text style={styles.errorText}>No financial profile found.</Text>
                )}
              </View>
            </View>
          )}

          <View style={styles.card}>
            <View style={styles.cardContent}>
              <Text style={styles.termsText}>
                By completing signup, you accept the{' '}
                <Text style={styles.linkText} onPress={handleOpenTerms}>
                  Terms of Service
                </Text>{' '}
                and{' '}
                <Text style={styles.linkText} onPress={handleOpenPrivacyPolicy}>
                  Privacy Policy
                </Text>
                . This experimental build does not provide a regulated identity-verification or transaction-monitoring
                service.
              </Text>
            </View>
            <View style={styles.buttonContainer}>
              {!canCompleteSignup && (
                <Text style={styles.validationText}>Please ensure all information is complete to proceed.</Text>
              )}
              <PrimaryButton
                onPress={completeSignup}
                loading={isSubmitting}
                disabled={!canCompleteSignup}
                fullWidth
                style={styles.completeButton}
              >
                Complete Signup
              </PrimaryButton>
            </View>
          </View>

          <View style={styles.divider}>
            <View style={styles.dividerLine} />
            <Text style={styles.dividerText}>or</Text>
            <View style={styles.dividerLine} />
          </View>

          <TouchableOpacity style={styles.backSection} onPress={handleBack} disabled={isSubmitting}>
            <Text style={styles.backLink}>Go Back</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    </GradientBackground>
  );
}
