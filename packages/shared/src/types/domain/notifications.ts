import type { BaseEntity } from '../common';

export type DeviceType = 'ios' | 'android';

export interface DeviceToken extends BaseEntity {
  pushToken: string;
  deviceType: DeviceType;
  isActive: boolean;
  lastUsedAt: string;
}

/* eslint-disable @typescript-eslint/naming-convention */
export interface RegisterDeviceTokenRequest {
  push_token: string;
  device_type: DeviceType;
}
/* eslint-enable @typescript-eslint/naming-convention */

/* eslint-disable @typescript-eslint/naming-convention */
export interface UnregisterDeviceTokenRequest {
  push_token: string;
}
/* eslint-enable @typescript-eslint/naming-convention */

export interface NotificationPreferences extends BaseEntity {
  userProfile: string;
  transactionAlerts: boolean;
  priceAlerts: boolean;
  marketing: boolean;
}

/* eslint-disable @typescript-eslint/naming-convention */
export interface UpdateNotificationPreferencesRequest {
  transaction_alerts?: boolean;
  price_alerts?: boolean;
  marketing?: boolean;
}
/* eslint-enable @typescript-eslint/naming-convention */

export type NotificationType = 'transaction' | 'price' | 'marketing' | 'general' | 'system';

export interface Notification extends BaseEntity {
  title: string;
  body: string;
  notificationType: NotificationType;
  data: Record<string, unknown>;
  isRead: boolean;
  readAt: string | null;
  isArchived: boolean;
}

export interface UnreadCountResponse {
  unreadCount: number;
}

export interface MarkAllReadResponse {
  marked: number;
}
