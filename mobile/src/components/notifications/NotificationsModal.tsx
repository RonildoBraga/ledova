import React, { useEffect } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { XIcon } from 'phosphor-react-native';
import { formatDateTime } from '@ledova/shared-utils';
import type { Notification } from '@ledova/shared-types';
import { useAppTheme, useThemedStyles } from '../../contexts';
import { CustomModal } from '../modal';
import { useNotifications } from '../../hooks/useNotifications';

interface NotificationsModalProps {
  visible: boolean;
  onClose: () => void;
}

function NotificationItem({
  notification,
  onRead,
  onArchive,
}: {
  notification: Notification;
  onRead: (uuid: string) => void;
  onArchive: (uuid: string) => void;
}) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    notificationItem: {
      flexDirection: 'row' as const,
      alignItems: 'flex-start' as const,
      paddingVertical: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    notificationContent: {
      flex: 1,
      flexDirection: 'row' as const,
      alignItems: 'flex-start' as const,
      gap: theme.spacing.sm,
    },
    unreadDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: theme.colors.interactive.active,
      marginTop: 6,
    },
    textContainer: {
      flex: 1,
    },
    textContainerRead: {
      paddingLeft: 16,
    },
    notificationTitle: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    notificationBody: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    notificationTime: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      marginTop: 4,
    },
    archiveButton: {
      padding: theme.spacing.xs,
      marginLeft: theme.spacing.xs,
    },
  }));
  return (
    <TouchableOpacity
      style={styles.notificationItem}
      onPress={() => {
        if (!notification.isRead) onRead(notification.uuid);
      }}
      activeOpacity={0.7}
    >
      <View style={styles.notificationContent}>
        {!notification.isRead && <View style={styles.unreadDot} />}
        <View style={[styles.textContainer, notification.isRead && styles.textContainerRead]}>
          <Text style={styles.notificationTitle} numberOfLines={1}>
            {notification.title}
          </Text>
          <Text style={styles.notificationBody} numberOfLines={2}>
            {notification.body}
          </Text>
          <Text style={styles.notificationTime}>{formatDateTime(notification.createdAt)}</Text>
        </View>
      </View>
      <TouchableOpacity
        style={styles.archiveButton}
        onPress={() => onArchive(notification.uuid)}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <XIcon size={16} color={theme.colors.text.muted} />
      </TouchableOpacity>
    </TouchableOpacity>
  );
}

export function NotificationsModal({ visible, onClose }: NotificationsModalProps) {
  const theme = useAppTheme();
  const styles = useThemedStyles((theme) => ({
    container: {
      paddingVertical: theme.spacing.sm,
      minHeight: 300,
      maxHeight: 500,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: theme.spacing.md,
    },
    title: {
      fontSize: theme.fontSize.xl,
      fontWeight: theme.fontWeight.semibold,
      color: theme.colors.text.primary,
    },
    markAllRead: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.interactive.active,
    },
    markAllReadDisabled: {
      opacity: 0.5,
    },
    loadingContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.xl,
    },
    emptyContainer: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: theme.spacing.xl,
    },
    emptyText: {
      fontSize: theme.fontSize.sm,
      color: theme.colors.text.muted,
    },
    list: {
      flex: 1,
    },
    notificationItem: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      paddingVertical: theme.spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: theme.colors.border.subtle,
    },
    notificationContent: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: theme.spacing.sm,
    },
    unreadDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: theme.colors.interactive.active,
      marginTop: 6,
    },
    textContainer: {
      flex: 1,
    },
    textContainerRead: {
      paddingLeft: 16,
    },
    notificationTitle: {
      fontSize: theme.fontSize.sm,
      fontWeight: theme.fontWeight.medium,
      color: theme.colors.text.primary,
    },
    notificationBody: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.muted,
      marginTop: 2,
    },
    notificationTime: {
      fontSize: theme.fontSize.xs,
      color: theme.colors.text.subtle,
      marginTop: 4,
    },
    archiveButton: {
      padding: theme.spacing.xs,
      marginLeft: theme.spacing.xs,
    },
  }));
  const {
    unreadCount,
    notifications,
    isLoadingNotifications,
    fetchNotifications,
    markAsRead,
    archive,
    markAllAsRead,
    isMarkingAllRead,
  } = useNotifications();

  useEffect(() => {
    if (visible) {
      fetchNotifications();
    }
  }, [visible, fetchNotifications]);

  return (
    <CustomModal visible={visible} onClose={onClose} showFooter={false}>
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Notifications</Text>
          {unreadCount > 0 && (
            <TouchableOpacity onPress={() => markAllAsRead()} disabled={isMarkingAllRead}>
              <Text style={[styles.markAllRead, isMarkingAllRead && styles.markAllReadDisabled]}>Mark all as read</Text>
            </TouchableOpacity>
          )}
        </View>

        {isLoadingNotifications && notifications.length === 0 ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="small" color={theme.colors.interactive.active} />
          </View>
        ) : notifications.length === 0 ? (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>No notifications yet</Text>
          </View>
        ) : (
          <ScrollView style={styles.list} showsVerticalScrollIndicator={false}>
            {notifications.map((notification: Notification) => (
              <NotificationItem
                key={notification.uuid}
                notification={notification}
                onRead={markAsRead}
                onArchive={archive}
              />
            ))}
          </ScrollView>
        )}
      </View>
    </CustomModal>
  );
}
