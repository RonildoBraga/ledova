import React, { useState, useCallback } from 'react';
import { View, Text, ScrollView, Alert, Switch, TouchableOpacity, TextInput } from 'react-native';
import {
  CaretRightIcon,
  EyeIcon,
  EyeSlashIcon,
  LockIcon,
  BellIcon,
  UserGearIcon,
  AppWindowIcon,
  SunIcon,
  MoonIcon,
  CurrencyCircleDollarIcon,
} from 'phosphor-react-native';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { upsertCurrentUserPreferences } from '@ledova/shared';
import type { DisplayCurrency } from '@ledova/shared';
import { GradientBackground } from '../../components/GradientBackground';
import { Panel } from '../../components/panel';
import { CustomModal } from '../../components/modal';
import { useAppLock, useAppTheme, useThemedStyles, useThemeMode } from '../../contexts';
import { useUserPreferences } from '../../hooks/useUserPreferences';
import { useNotificationPreferences } from './useNotificationPreferences';
import { useSettings } from './useSettings';
import { apiClient } from '../../services/apiClient';

interface ToggleRowProps {
  label: string;
  description?: string;
  value: boolean;
  onValueChange: (value: boolean) => void;
  disabled?: boolean;
  isLast?: boolean;
}

function ToggleRow({ label, description, value, onValueChange, disabled = false, isLast = false }: ToggleRowProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.md,
    },
    rowBorder: {
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    rowTextContainer: {
      flex: 1,
      marginRight: theme.spacing.md,
    },
    rowLabel: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
    },
    rowLabelDisabled: {
      color: theme.colors.text.muted,
    },
    rowDescription: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    rowDescriptionDisabled: {
      color: theme.colors.text.muted,
    },
  }));
  return (
    <TouchableOpacity
      style={[styles.row, !isLast && styles.rowBorder]}
      onPress={() => !disabled && onValueChange(!value)}
      activeOpacity={disabled ? 1 : 0.7}
      disabled={disabled}
    >
      <View style={styles.rowTextContainer}>
        <Text style={[styles.rowLabel, disabled && styles.rowLabelDisabled]}>{label}</Text>
        {description && (
          <Text style={[styles.rowDescription, disabled && styles.rowDescriptionDisabled]}>{description}</Text>
        )}
      </View>
      <Switch
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        trackColor={{
          false: theme.colors.surface.disabled,
          true: theme.colors.interactive.default,
        }}
        thumbColor={theme.colors.utility.white}
        ios_backgroundColor={theme.colors.surface.disabled}
      />
    </TouchableOpacity>
  );
}

interface NavRowProps {
  label: string;
  onPress: () => void;
  danger?: boolean;
  isLast?: boolean;
}

function NavRow({ label, onPress, danger = false, isLast = false }: NavRowProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.md,
    },
    rowBorder: {
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    rowLabel: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
    },
    rowLabelDanger: {
      color: theme.colors.status.error.icon,
    },
  }));
  return (
    <TouchableOpacity style={[styles.row, !isLast && styles.rowBorder]} onPress={onPress} activeOpacity={0.7}>
      <Text style={[styles.rowLabel, danger && styles.rowLabelDanger]}>{label}</Text>
      <CaretRightIcon size={20} color={theme.colors.text.muted} weight="regular" />
    </TouchableOpacity>
  );
}

interface CurrencyRowProps {
  value: DisplayCurrency;
  onSelect: (currency: DisplayCurrency) => void;
  disabled?: boolean;
}

function CurrencyRow({ value, onSelect, disabled = false }: CurrencyRowProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.md,
    },
    rowLabel: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
    },
    segmentContainer: {
      flexDirection: 'row',
      borderRadius: theme.borderRadius.lg,
      borderWidth: 1,
      borderColor: theme.colors.border.default,
      overflow: 'hidden',
    },
    segment: {
      paddingVertical: theme.spacing.xs,
      paddingHorizontal: theme.spacing.md,
    },
    segmentActive: {
      backgroundColor: theme.colors.interactive.default,
    },
    segmentText: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.muted,
    },
    segmentTextActive: {
      color: theme.colors.utility.white,
    },
  }));

  const options: DisplayCurrency[] = ['AUD', 'USD'];

  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>Display Currency</Text>
      <View style={styles.segmentContainer}>
        {options.map((currency) => (
          <TouchableOpacity
            key={currency}
            style={[styles.segment, value === currency && styles.segmentActive]}
            onPress={() => !disabled && onSelect(currency)}
            activeOpacity={disabled ? 1 : 0.7}
            disabled={disabled}
          >
            <Text style={[styles.segmentText, value === currency && styles.segmentTextActive]}>{currency}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

export function SettingsScreen() {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      flex: 1,
    },
    scrollView: {
      flex: 1,
    },
    content: {
      paddingTop: theme.spacing.md,
      paddingHorizontal: theme.spacing.sm,
      gap: theme.spacing.md,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: theme.spacing.md,
      paddingVertical: theme.spacing.md,
    },
    rowBorder: {
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.default,
    },
    rowTextContainer: {
      flex: 1,
      marginRight: theme.spacing.md,
    },
    rowLabel: {
      fontSize: theme.fontSize.base,
      color: theme.colors.text.primary,
    },
    rowLabelDisabled: {
      color: theme.colors.text.muted,
    },
    rowLabelDanger: {
      color: theme.colors.status.error.icon,
    },
    rowDescription: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    rowDescriptionDisabled: {
      color: theme.colors.text.muted,
    },
    modalContent: {
      gap: theme.spacing.sm,
    },
    modalTitle: {
      fontSize: theme.fontSize.lg,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
      marginBottom: theme.spacing.xs,
    },
    modalText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.body,
      lineHeight: 20,
    },
    modalTextDanger: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.status.error.icon,
      fontWeight: theme.fontWeight.semibold,
      lineHeight: 20,
    },
    modalTextHint: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: theme.spacing.xs,
    },
    inputContainer: {
      marginTop: theme.spacing.sm,
    },
    inputLabel: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.body,
      marginBottom: theme.spacing.xs,
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
    input: {
      flex: 1,
      color: theme.colors.text.primary,
      fontSize: theme.fontSize.base,
    },
    eyeButton: {
      padding: theme.spacing.xs,
      marginLeft: theme.spacing.xs,
    },
  }));

  const { themeMode, toggleTheme } = useThemeMode();
  const { preferences } = useUserPreferences();
  const queryClient = useQueryClient();
  const displayCurrency: DisplayCurrency = preferences?.displayCurrency ?? 'AUD';

  const currencyMutation = useMutation({
    mutationFn: (currency: DisplayCurrency) => upsertCurrentUserPreferences(apiClient, { displayCurrency: currency }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['userPreferences'] });
      queryClient.invalidateQueries({ queryKey: ['exchangeRate'] });
    },
  });

  const {
    isEnabled: appLockEnabled,
    setEnabled: setAppLockEnabled,
    hasBiometricLogin,
    enableBiometricLogin,
    disableBiometricLogin,
    biometricsAvailable,
    biometricType,
  } = useAppLock();

  const {
    transactionAlerts,
    priceAlerts,
    marketing,
    toggleTransactionAlerts,
    togglePriceAlerts,
    toggleMarketing,
    isUpdating,
  } = useNotificationPreferences();

  const {
    changeUserPassword,
    isChangingPassword,
    exportData,
    isExporting,
    deleteUserAccount,
    isDeleting,
    rateApp,
    shareApp,
  } = useSettings();

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showChangePasswordModal, setShowChangePasswordModal] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const handleAppLockToggle = useCallback(
    async (value: boolean) => {
      const success = await setAppLockEnabled(value);
      if (!success && value) {
        Alert.alert('Authentication Failed', `Could not enable ${biometricType} lock. Please try again.`, [
          { text: 'OK' },
        ]);
      }
    },
    [setAppLockEnabled, biometricType],
  );

  const handleBiometricLoginToggle = useCallback(
    async (value: boolean) => {
      if (value) {
        const success = await enableBiometricLogin();
        if (!success) {
          Alert.alert('Authentication Failed', `Could not enable ${biometricType} sign in. Please try again.`, [
            { text: 'OK' },
          ]);
        }
      } else {
        Alert.alert(
          `Disable ${biometricType} Sign In`,
          'You will need to enter your email and password next time you sign in.',
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Disable',
              style: 'destructive',
              onPress: async () => {
                await disableBiometricLogin();
              },
            },
          ],
        );
      }
    },
    [enableBiometricLogin, disableBiometricLogin, biometricType],
  );

  const handleChangePassword = async () => {
    if (!currentPassword || !newPassword || !confirmPassword) {
      Alert.alert('Error', 'Please fill in all fields.');
      return;
    }
    if (newPassword !== confirmPassword) {
      Alert.alert('Error', 'New passwords do not match.');
      return;
    }
    if (newPassword.length < 8) {
      Alert.alert('Error', 'New password must be at least 8 characters long.');
      return;
    }

    const success = await changeUserPassword(currentPassword, newPassword, confirmPassword);
    if (success) {
      setShowChangePasswordModal(false);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    }
  };

  const handleExportData = async () => {
    const success = await exportData();
    if (success) {
      setShowExportModal(false);
    }
  };

  const handleDeleteAccount = async () => {
    await deleteUserAccount();
    setShowDeleteModal(false);
  };

  return (
    <GradientBackground>
      <View style={styles.container}>
        <ScrollView style={styles.scrollView} showsVerticalScrollIndicator={false}>
          <View style={styles.content}>
            <Panel title="Security" icon={<LockIcon />}>
              <ToggleRow
                label={`${biometricType} Sign In`}
                description={`Sign in with ${biometricType} instead of password`}
                value={hasBiometricLogin}
                onValueChange={handleBiometricLoginToggle}
                disabled={!biometricsAvailable}
              />
              <ToggleRow
                label="App Lock"
                description={`Lock app with ${biometricType} after background`}
                value={appLockEnabled}
                onValueChange={handleAppLockToggle}
                disabled={!biometricsAvailable}
                isLast
              />
            </Panel>

            <Panel title="Notifications" icon={<BellIcon />}>
              <ToggleRow
                label="Transaction Alerts"
                description="Notifications for transaction status changes"
                value={transactionAlerts}
                onValueChange={toggleTransactionAlerts}
                disabled={isUpdating}
              />
              <ToggleRow
                label="Price Alerts"
                description="Notifications for price threshold alerts"
                value={priceAlerts}
                onValueChange={togglePriceAlerts}
                disabled={isUpdating}
              />
              <ToggleRow
                label="Marketing"
                description="Marketing and promotional notifications"
                value={marketing}
                onValueChange={toggleMarketing}
                disabled={isUpdating}
                isLast
              />
            </Panel>

            <Panel title="Account" icon={<UserGearIcon />}>
              <NavRow label="Change Password" onPress={() => setShowChangePasswordModal(true)} />
              <NavRow label="Export Data" onPress={() => setShowExportModal(true)} />
              <NavRow label="Delete Account" onPress={() => setShowDeleteModal(true)} danger isLast />
            </Panel>

            <Panel title="Appearance" icon={themeMode === 'dark' ? <MoonIcon /> : <SunIcon />}>
              <ToggleRow
                label="Light Mode"
                description={themeMode === 'dark' ? 'Currently using dark theme' : 'Currently using light theme'}
                value={themeMode === 'light'}
                onValueChange={() => toggleTheme()}
              />
              <CurrencyRow
                value={displayCurrency}
                onSelect={(currency) => currencyMutation.mutate(currency)}
                disabled={currencyMutation.isPending}
              />
            </Panel>

            <Panel title="App" icon={<AppWindowIcon />}>
              <NavRow label="Rate the App" onPress={rateApp} />
              <NavRow label="Share with Friends" onPress={shareApp} isLast />
            </Panel>
          </View>
        </ScrollView>
      </View>

      <CustomModal
        visible={showExportModal}
        onClose={() => setShowExportModal(false)}
        showFooter
        confirmLabel="Export"
        onConfirm={handleExportData}
        confirmLoading={isExporting}
      >
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>Export Your Data</Text>
          <Text style={styles.modalText}>
            This will export all your account data including your profile, wallets, transactions, and portfolios as a
            JSON file.
          </Text>
          <Text style={styles.modalText}>You can save or share this file for your records.</Text>
        </View>
      </CustomModal>

      <CustomModal
        visible={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        showFooter
        confirmLabel="Delete Account"
        onConfirm={handleDeleteAccount}
        confirmLoading={isDeleting}
      >
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>Delete Account</Text>
          <Text style={styles.modalTextDanger}>This action cannot be undone.</Text>
          <Text style={styles.modalText}>
            Deleting your account will permanently remove your profile and personal information. Your transaction
            history will be retained for compliance purposes.
          </Text>
          <Text style={styles.modalText}>Are you sure you want to delete your account?</Text>
        </View>
      </CustomModal>

      <CustomModal
        visible={showChangePasswordModal}
        onClose={() => {
          setShowChangePasswordModal(false);
          setCurrentPassword('');
          setNewPassword('');
          setConfirmPassword('');
        }}
        showFooter
        confirmLabel="Change Password"
        onConfirm={handleChangePassword}
        confirmLoading={isChangingPassword}
      >
        <View style={styles.modalContent}>
          <Text style={styles.modalTitle}>Change Password</Text>
          <Text style={styles.modalText}>Enter your current password and choose a new one.</Text>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Current Password</Text>
            <View style={styles.inputWrapper}>
              <TextInput
                style={styles.input}
                placeholder="Enter current password"
                placeholderTextColor={theme.colors.text.muted}
                value={currentPassword}
                onChangeText={setCurrentPassword}
                secureTextEntry={!showCurrentPassword}
                autoCapitalize="none"
              />
              <TouchableOpacity onPress={() => setShowCurrentPassword(!showCurrentPassword)} style={styles.eyeButton}>
                {showCurrentPassword ? (
                  <EyeSlashIcon size={20} color={theme.colors.text.muted} />
                ) : (
                  <EyeIcon size={20} color={theme.colors.text.muted} />
                )}
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>New Password</Text>
            <View style={styles.inputWrapper}>
              <TextInput
                style={styles.input}
                placeholder="Enter new password"
                placeholderTextColor={theme.colors.text.muted}
                value={newPassword}
                onChangeText={setNewPassword}
                secureTextEntry={!showNewPassword}
                autoCapitalize="none"
              />
              <TouchableOpacity onPress={() => setShowNewPassword(!showNewPassword)} style={styles.eyeButton}>
                {showNewPassword ? (
                  <EyeSlashIcon size={20} color={theme.colors.text.muted} />
                ) : (
                  <EyeIcon size={20} color={theme.colors.text.muted} />
                )}
              </TouchableOpacity>
            </View>
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.inputLabel}>Confirm New Password</Text>
            <View style={styles.inputWrapper}>
              <TextInput
                style={styles.input}
                placeholder="Confirm new password"
                placeholderTextColor={theme.colors.text.muted}
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                secureTextEntry={!showConfirmPassword}
                autoCapitalize="none"
              />
              <TouchableOpacity onPress={() => setShowConfirmPassword(!showConfirmPassword)} style={styles.eyeButton}>
                {showConfirmPassword ? (
                  <EyeSlashIcon size={20} color={theme.colors.text.muted} />
                ) : (
                  <EyeIcon size={20} color={theme.colors.text.muted} />
                )}
              </TouchableOpacity>
            </View>
          </View>

          <Text style={styles.modalTextHint}>Password must be at least 8 characters long.</Text>
        </View>
      </CustomModal>
    </GradientBackground>
  );
}
