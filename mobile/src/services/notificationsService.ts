/**
 * Notifications Service
 *
 * Handles push notification setup and token registration.
 */

import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { registerDeviceToken, unregisterDeviceToken } from '@ledova/shared';
import type { DeviceType } from '@ledova/shared';
import { apiClient } from './apiClient';

const PUSH_TOKEN_KEY = 'notifications.pushToken';

/**
 * Notifications service for managing push notifications.
 */
export const notificationsService = {
  /**
   * Configure notification handler for foreground notifications.
   * Call this early in the app initialization.
   */
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

  /**
   * Get the Expo push token for this device.
   * Requests permissions if not already granted.
   */
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

  /**
   * Register the device token with the backend.
   */
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

  /**
   * Unregister the device token from the backend.
   */
  async unregisterToken(): Promise<void> {
    const token = await SecureStore.getItemAsync(PUSH_TOKEN_KEY).catch(() => null);
    if (!token) {
      return;
    }
    try {
      await unregisterDeviceToken(apiClient, { push_token: token });
    } catch {
      // Best effort: the backend drops the token on the next sign-in anyway.
    } finally {
      // The stored key belongs to this session; a failed unregister must not keep it around.
      await SecureStore.deleteItemAsync(PUSH_TOKEN_KEY).catch(() => undefined);
    }
  },
};
