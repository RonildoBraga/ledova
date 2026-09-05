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

export const registerDeviceToken = (apiClient: AxiosInstance, data: RegisterDeviceTokenRequest) => {
  return apiClient.post<DeviceToken>(DEVICE_TOKEN_ENDPOINTS.REGISTER, data);
};

export const unregisterDeviceToken = (apiClient: AxiosInstance, data: UnregisterDeviceTokenRequest) => {
  return apiClient.post<void>(DEVICE_TOKEN_ENDPOINTS.UNREGISTER, data);
};

export const getNotificationPreferences = (apiClient: AxiosInstance) => {
  return apiClient.get<NotificationPreferences>(NOTIFICATION_PREFERENCES_ENDPOINTS.BASE);
};

export const updateNotificationPreferences = (apiClient: AxiosInstance, data: UpdateNotificationPreferencesRequest) => {
  return apiClient.post<NotificationPreferences>(NOTIFICATION_PREFERENCES_ENDPOINTS.BASE, data);
};

export const getNotifications = (apiClient: AxiosInstance) => {
  return apiClient.get<PaginatedResponse<Notification>>(NOTIFICATION_ENDPOINTS.BASE);
};

export const getUnreadNotificationCount = (apiClient: AxiosInstance) => {
  return apiClient.get<UnreadCountResponse>(NOTIFICATION_ENDPOINTS.UNREAD_COUNT);
};

export const markNotificationRead = (apiClient: AxiosInstance, uuid: string) => {
  return apiClient.patch<Notification>(NOTIFICATION_ENDPOINTS.DETAIL(uuid), { is_read: true });
};

export const archiveNotification = (apiClient: AxiosInstance, uuid: string) => {
  return apiClient.patch<Notification>(NOTIFICATION_ENDPOINTS.DETAIL(uuid), { is_archived: true });
};

export const markAllNotificationsRead = (apiClient: AxiosInstance) => {
  return apiClient.post<MarkAllReadResponse>(NOTIFICATION_ENDPOINTS.MARK_ALL_READ);
};
