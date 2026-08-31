import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Modal,
  Pressable,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { GradientBackground } from '../../../components/GradientBackground';
import { PrimaryButton } from '../../../components/buttons';
import { ScreenHeader } from '../../../components/header';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import type { RootStackParamList } from '../../../navigation/AppNavigator';
import { useCompanyRegistration } from './useCompanyRegistration';
import { BuildingsIcon, WarningCircleIcon, CaretDownIcon, CheckIcon } from 'phosphor-react-native';
import { layout } from '../../../styles';
import { useAppTheme, useThemedStyles, overlayColors } from '../../../contexts';

const COMPANY_TYPES = [
  { value: 'pty', label: 'Proprietary Limited (Pty Ltd)', short: 'Pty Ltd' },
  { value: 'public', label: 'Public Company (Ltd)', short: 'Public (Ltd)' },
  { value: 'unlisted', label: 'Unlisted Public Company', short: 'Unlisted Public' },
];

export function CompanyRegistrationScreen() {
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
    errorStateContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      padding: theme.spacing.lg,
      gap: theme.spacing.md,
    },
    errorStateTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    errorStateMessage: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      textAlign: 'center',
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
    inputWrapper: {
      position: 'relative',
    },
    inputIcon: {
      position: 'absolute',
      left: theme.spacing.md,
      top: 14,
      zIndex: 1,
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
    inputError: {
      borderColor: theme.colors.status.error.text,
      backgroundColor: theme.colors.error.subtle,
    },
    fieldError: {
      color: theme.colors.status.error.icon,
      fontSize: theme.fontSize.xs,
      marginTop: theme.spacing.xs,
    },
    selectTrigger: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      backgroundColor: theme.colors.surface.tertiary,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      borderRadius: theme.borderRadius.md,
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.md,
      height: 48,
    },
    selectTriggerText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
      flex: 1,
      marginRight: theme.spacing.sm,
    },
    modalOverlay: {
      flex: 1,
      backgroundColor: overlayColors.modal,
      justifyContent: 'center',
      paddingHorizontal: theme.spacing.xl,
    },
    modalContent: {
      backgroundColor: theme.colors.surface.raised,
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      padding: theme.spacing.lg,
    },
    modalTitle: {
      fontSize: theme.fontSize.base,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.md,
    },
    modalOption: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: 14,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    modalOptionText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.primary,
      flex: 1,
    },
    modalOptionTextSelected: {
      color: theme.colors.interactive.active,
      fontWeight: theme.fontWeight.medium,
    },
    row: {
      flexDirection: 'row',
      gap: theme.spacing.md,
    },
    flex1: {
      flex: 1,
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
  const { form, errors, generalError, isLoading, isSubmitting, setFieldValue, handleSubmit, retryLoad } =
    useCompanyRegistration();
  const [showTypePicker, setShowTypePicker] = useState(false);

  const selectedType = COMPANY_TYPES.find((t) => t.value === form.companyType);
  const selectedTypeLabel = selectedType?.label || 'Select type';

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
          <Text style={styles.loadingText}>Loading company data...</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (generalError && !form.name && !isSubmitting) {
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
            <ScreenHeader
              icon={
                <BuildingsIcon
                  size={theme.icon.sizes.md}
                  color={theme.colors.text.muted}
                  weight={theme.icon.weights.regular}
                />
              }
              title="Company Details"
              subtitle="Enter your company's basic information"
            />

            <View style={styles.formContainer}>
              {generalError && isSubmitting === false && form.name ? (
                <View style={styles.errorContainer}>
                  <WarningCircleIcon
                    size={theme.icon.sizes.md}
                    color={theme.colors.status.error.icon}
                    weight={theme.icon.weights.regular}
                  />
                  <Text style={styles.errorText}>{generalError}</Text>
                </View>
              ) : null}

              <View style={styles.fieldContainer}>
                <Text style={styles.label}>Company Name *</Text>
                <View style={styles.inputWrapper}>
                  <View style={styles.inputIcon}>
                    <BuildingsIcon
                      size={theme.icon.sizes.md}
                      color={theme.colors.text.subtle}
                      weight={theme.icon.weights.regular}
                    />
                  </View>
                  <TextInput
                    style={[styles.input, styles.inputWithIcon, errors.name && styles.inputError]}
                    value={form.name}
                    onChangeText={(value) => setFieldValue('name', value)}
                    placeholder="Your Company Pty Ltd"
                    placeholderTextColor={theme.colors.text.muted}
                    autoCapitalize="words"
                    editable={!isSubmitting}
                  />
                </View>
                {errors.name && <Text style={styles.fieldError}>{errors.name[0]}</Text>}
              </View>

              <View style={styles.fieldContainer}>
                <Text style={styles.label}>Trading Name (optional)</Text>
                <TextInput
                  style={styles.input}
                  value={form.tradingName}
                  onChangeText={(value) => setFieldValue('tradingName', value)}
                  placeholder="Trading as..."
                  placeholderTextColor={theme.colors.text.muted}
                  autoCapitalize="words"
                  editable={!isSubmitting}
                />
              </View>

              <View style={styles.fieldContainer}>
                <Text style={styles.label}>Company Type *</Text>
                <TouchableOpacity
                  style={styles.selectTrigger}
                  onPress={() => setShowTypePicker(true)}
                  disabled={isSubmitting}
                >
                  <Text style={styles.selectTriggerText} numberOfLines={1}>
                    {selectedTypeLabel}
                  </Text>
                  <CaretDownIcon size={16} color={theme.colors.text.muted} weight="bold" />
                </TouchableOpacity>
              </View>

              <View style={styles.row}>
                <View style={[styles.fieldContainer, styles.flex1]}>
                  <Text style={styles.label}>ACN *</Text>
                  <TextInput
                    style={[styles.input, errors.acn && styles.inputError]}
                    value={form.acn}
                    onChangeText={(value) => setFieldValue('acn', value)}
                    placeholder="123 456 789"
                    placeholderTextColor={theme.colors.text.muted}
                    keyboardType="number-pad"
                    maxLength={11}
                    editable={!isSubmitting}
                  />
                  {errors.acn && <Text style={styles.fieldError}>{errors.acn[0]}</Text>}
                </View>

                <View style={[styles.fieldContainer, styles.flex1]}>
                  <Text style={styles.label}>ABN (optional)</Text>
                  <TextInput
                    style={[styles.input, errors.abn && styles.inputError]}
                    value={form.abn}
                    onChangeText={(value) => setFieldValue('abn', value)}
                    placeholder="12 345 678 901"
                    placeholderTextColor={theme.colors.text.muted}
                    keyboardType="number-pad"
                    maxLength={14}
                    editable={!isSubmitting}
                  />
                  {errors.abn && <Text style={styles.fieldError}>{errors.abn[0]}</Text>}
                </View>
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
      <Modal visible={showTypePicker} transparent animationType="fade" onRequestClose={() => setShowTypePicker(false)}>
        <Pressable style={styles.modalOverlay} onPress={() => setShowTypePicker(false)}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Company Type</Text>
            {COMPANY_TYPES.map((type) => (
              <TouchableOpacity
                key={type.value}
                style={styles.modalOption}
                onPress={() => {
                  setFieldValue('companyType', type.value);
                  setShowTypePicker(false);
                }}
              >
                <Text
                  style={[styles.modalOptionText, form.companyType === type.value && styles.modalOptionTextSelected]}
                >
                  {type.label}
                </Text>
                {form.companyType === type.value && (
                  <CheckIcon size={18} color={theme.colors.interactive.active} weight="bold" />
                )}
              </TouchableOpacity>
            ))}
          </View>
        </Pressable>
      </Modal>
    </GradientBackground>
  );
}
