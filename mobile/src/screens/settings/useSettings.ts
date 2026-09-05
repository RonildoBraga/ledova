import { useState, useCallback } from 'react';
import { Alert, Linking, Share } from 'react-native';
import * as StoreReview from 'expo-store-review';
import { useNavigation, NavigationProp } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { deleteAccount, exportAccountData, changePassword } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';
import { clearTokens } from '../../services/tokenStorage';
import type { RootStackParamList } from '../../navigation/AppNavigator';
import { APP_STORE_URL, MARKETING_URL } from '../../config/publicLinks';

export function useSettings() {
  const navigation = useNavigation<NavigationProp<RootStackParamList>>();
  const queryClient = useQueryClient();

  const [isExporting, setIsExporting] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  const changeUserPassword = useCallback(
    async (currentPassword: string, newPassword: string, newPasswordConfirm: string): Promise<boolean> => {
      setIsChangingPassword(true);
      try {
        await changePassword(apiClient, {
          currentPassword,
          newPassword,
          newPasswordConfirm,
        });

        Alert.alert('Password Changed', 'Your password has been changed successfully.');
        return true;
      } catch (error: unknown) {
        const errorResponse = error as { response?: { data?: Record<string, string[]> } };
        const errorData = errorResponse?.response?.data;

        if (errorData?.current_password) {
          Alert.alert('Error', errorData.current_password[0] || 'Current password is incorrect.');
        } else if (errorData?.new_password) {
          Alert.alert('Error', errorData.new_password[0] || 'Invalid new password.');
        } else if (errorData?.new_password_confirm) {
          Alert.alert('Error', errorData.new_password_confirm[0] || 'Passwords do not match.');
        } else {
          Alert.alert('Error', 'Unable to change password. Please try again later.');
        }
        return false;
      } finally {
        setIsChangingPassword(false);
      }
    },
    [],
  );

  const exportData = useCallback(async (): Promise<boolean> => {
    setIsExporting(true);
    try {
      const response = await exportAccountData(apiClient);
      const data = response.data;

      const jsonString = JSON.stringify(data, null, 2);
      await Share.share({
        message: jsonString,
        title: 'Ledova - Account Data Export',
      });

      return true;
    } catch {
      Alert.alert('Export Failed', 'Unable to export your data. Please try again later.');
      return false;
    } finally {
      setIsExporting(false);
    }
  }, []);

  const deleteUserAccount = useCallback(async (): Promise<boolean> => {
    setIsDeleting(true);
    try {
      await deleteAccount(apiClient);

      await clearTokens();
      queryClient.clear();

      navigation.reset({
        index: 0,
        routes: [{ name: 'SignIn' }],
      });

      return true;
    } catch {
      Alert.alert('Delete Failed', 'Unable to delete your account. Please try again later.');
      return false;
    } finally {
      setIsDeleting(false);
    }
  }, [navigation, queryClient]);

  const rateApp = useCallback(async () => {
    const isAvailable = await StoreReview.isAvailableAsync();
    if (isAvailable) {
      await StoreReview.requestReview();
    } else if (APP_STORE_URL) {
      await Linking.openURL(APP_STORE_URL);
    } else {
      Alert.alert('Unavailable', 'No app-store listing is configured for this build.');
    }
  }, []);

  const shareApp = useCallback(async () => {
    try {
      await Share.share({
        message: `Explore the Ledova experimental reference implementation: ${MARKETING_URL}`,
        title: 'Share Ledova',
      });
    } catch {}
  }, []);

  return {
    changeUserPassword,
    isChangingPassword,

    exportData,
    isExporting,

    deleteUserAccount,
    isDeleting,

    rateApp,
    shareApp,
  };
}
