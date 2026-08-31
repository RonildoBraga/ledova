import type { BaseEntity } from '../common';

/**
 * Device types for push tokens.
 */
export type DeviceType = 'ios' | 'android';

/**
 * Device token representing a device that can receive push notifications.
 */
export interface DeviceToken extends BaseEntity {
  pushToken: string;
  deviceType: DeviceType;
  isActive: boolean;
  lastUsedAt: string;
}

/**
 * Request payload for registering a device token.
 * Uses snake_case to match backend API format.
 */
/* eslint-disable @typescript-eslint/naming-convention */
export interface RegisterDeviceTokenRequest {
  push_token: string;
  device_type: DeviceType;
}
/* eslint-enable @typescript-eslint/naming-convention */

/**
 * Request payload for unregistering a device token.
 * Uses snake_case to match backend API format.
 */
/* eslint-disable @typescript-eslint/naming-convention */
export interface UnregisterDeviceTokenRequest {
  push_token: string;
}
/* eslint-enable @typescript-eslint/naming-convention */

/**
 * User notification preferences.
 */
export interface NotificationPreferences extends BaseEntity {
  userProfile: string;
  transactionAlerts: boolean;
  priceAlerts: boolean;
  marketing: boolean;
}

/**
 * Request payload for updating notification preferences.
 * Uses snake_case to match backend API format.
 */
/* eslint-disable @typescript-eslint/naming-convention */
export interface UpdateNotificationPreferencesRequest {
  transaction_alerts?: boolean;
  price_alerts?: boolean;
  marketing?: boolean;
}
/* eslint-enable @typescript-eslint/naming-convention */

/**
 * Response type for device token operations.
 */
export interface DeviceTokenResponse {
  success: boolean;
  data?: DeviceToken;
  message?: string;
}

/**
 * Response type for notification preferences operations.
 */
export interface NotificationPreferencesResponse {
  success: boolean;
  data?: NotificationPreferences;
  message?: string;
}

// =====================================================
// IN-APP NOTIFICATIONS
// =====================================================

/**
 * Notification type categories matching backend choices.
 */
export type NotificationType = 'transaction' | 'price' | 'marketing' | 'general' | 'system';

/**
 * In-app notification record.
 */
export interface Notification extends BaseEntity {
  title: string;
  body: string;
  notificationType: NotificationType;
  data: Record<string, unknown>;
  isRead: boolean;
  readAt: string | null;
  isArchived: boolean;
}

/**
 * Response for unread notification count.
 */
export interface UnreadCountResponse {
  unreadCount: number;
}

/**
 * Response for mark-all-read action.
 */
export interface MarkAllReadResponse {
  marked: number;
}
