import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { registerDeviceToken, unregisterDeviceToken } from '@ledova/shared';
import type { DeviceType } from '@ledova/shared';
import { apiClient } from './apiClient';

const PUSH_TOKEN_KEY = 'notifications.pushToken';

export const notificationsService = {
  configure(): void {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: true,
        shouldShowBanner: true,
        shouldShowList: true,
      }),
    });
  },

  async getToken(): Promise<string | null> {
    try {
      const { status: existingStatus } = await Notifications.getPermissionsAsync();
      let finalStatus = existingStatus;

      if (existingStatus !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync();
        finalStatus = status;
      }

      if (finalStatus !== 'granted') {
        return null;
      }

      const projectId = Constants.expoConfig?.extra?.eas?.projectId;
      if (!projectId) {
        return null;
      }

      const tokenData = await Notifications.getExpoPushTokenAsync({
        projectId,
      });

      return tokenData.data;
    } catch {
      return null;
    }
  },

  async registerToken(): Promise<boolean> {
    try {
      const token = await this.getToken();
      if (!token) {
        return false;
      }

      await registerDeviceToken(apiClient, {
        push_token: token,
        device_type: Platform.OS as DeviceType,
      });

      await SecureStore.setItemAsync(PUSH_TOKEN_KEY, token);
      return true;
    } catch {
      return false;
    }
  },

  async unregisterToken(): Promise<void> {
    const token = await SecureStore.getItemAsync(PUSH_TOKEN_KEY).catch(() => null);
    if (!token) {
      return;
    }
    try {
      await unregisterDeviceToken(apiClient, { push_token: token });
    } catch {
    } finally {
      await SecureStore.deleteItemAsync(PUSH_TOKEN_KEY).catch(() => undefined);
    }
  },
};
