import { AxiosInstance } from 'axios';
import { DEVICE_TOKEN_ENDPOINTS, NOTIFICATION_ENDPOINTS, NOTIFICATION_PREFERENCES_ENDPOINTS } from '../constants';
import type {
  DeviceToken,
  RegisterDeviceTokenRequest,
  UnregisterDeviceTokenRequest,
  NotificationPreferences,
  UpdateNotificationPreferencesRequest,
  Notification,
  PaginatedResponse,
  UnreadCountResponse,
  MarkAllReadResponse,
} from '../types';

/**
 * Register a device push token for the current user.
 */
export const registerDeviceToken = (apiClient: AxiosInstance, data: RegisterDeviceTokenRequest) => {
  return apiClient.post<DeviceToken>(DEVICE_TOKEN_ENDPOINTS.REGISTER, data);
};

/**
 * Unregister a device push token.
 */
export const unregisterDeviceToken = (apiClient: AxiosInstance, data: UnregisterDeviceTokenRequest) => {
  return apiClient.post<void>(DEVICE_TOKEN_ENDPOINTS.UNREGISTER, data);
};

/**
 * Get the current user's notification preferences.
 */
export const getNotificationPreferences = (apiClient: AxiosInstance) => {
  return apiClient.get<NotificationPreferences>(NOTIFICATION_PREFERENCES_ENDPOINTS.BASE);
};

/**
 * Update the current user's notification preferences.
 */
export const updateNotificationPreferences = (apiClient: AxiosInstance, data: UpdateNotificationPreferencesRequest) => {
  return apiClient.post<NotificationPreferences>(NOTIFICATION_PREFERENCES_ENDPOINTS.BASE, data);
};

// =====================================================
// IN-APP NOTIFICATIONS
// =====================================================

/**
 * Get paginated list of in-app notifications for the current user.
 */
export const getNotifications = (apiClient: AxiosInstance) => {
  return apiClient.get<PaginatedResponse<Notification>>(NOTIFICATION_ENDPOINTS.BASE);
};

/**
 * Get unread notification count for the current user.
 */
export const getUnreadNotificationCount = (apiClient: AxiosInstance) => {
  return apiClient.get<UnreadCountResponse>(NOTIFICATION_ENDPOINTS.UNREAD_COUNT);
};

/**
 * Mark a single notification as read.
 */
export const markNotificationRead = (apiClient: AxiosInstance, uuid: string) => {
  return apiClient.patch<Notification>(NOTIFICATION_ENDPOINTS.DETAIL(uuid), { is_read: true });
};

/**
 * Archive a single notification (removes it from the inbox).
 */
export const archiveNotification = (apiClient: AxiosInstance, uuid: string) => {
  return apiClient.patch<Notification>(NOTIFICATION_ENDPOINTS.DETAIL(uuid), { is_archived: true });
};

/**
 * Mark all unread notifications as read.
 */
export const markAllNotificationsRead = (apiClient: AxiosInstance) => {
  return apiClient.post<MarkAllReadResponse>(NOTIFICATION_ENDPOINTS.MARK_ALL_READ);
};
