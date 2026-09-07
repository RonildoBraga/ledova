import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CACHE_TIMING } from '../constants/api';
import {
  archiveNotification,
  getNotifications,
  getUnreadNotificationCount,
  markAllNotificationsRead,
  markNotificationRead,
} from '../services/notifications';
import { useApiClient } from './useApiClient';

export function useNotifications() {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();

  const unreadCountQuery = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => getUnreadNotificationCount(apiClient),
    staleTime: CACHE_TIMING.VERY_SHORT_STALE_TIME,
    refetchInterval: 60 * 1000,
  });

  const notificationsQuery = useQuery({
    queryKey: ['notifications', 'list'],
    queryFn: () => getNotifications(apiClient),
    staleTime: CACHE_TIMING.VERY_SHORT_STALE_TIME,
    enabled: false,
  });

  const markReadMutation = useMutation({
    mutationFn: (uuid: string) => markNotificationRead(apiClient, uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (uuid: string) => archiveNotification(apiClient, uuid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => markAllNotificationsRead(apiClient),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  return {
    unreadCount: unreadCountQuery.data?.data?.unreadCount ?? 0,
    notifications: notificationsQuery.data?.data?.results ?? [],
    isLoadingNotifications: notificationsQuery.isLoading || notificationsQuery.isFetching,
    fetchNotifications: notificationsQuery.refetch,
    markAsRead: markReadMutation.mutate,
    archive: archiveMutation.mutate,
    markAllAsRead: markAllReadMutation.mutate,
    isMarkingAllRead: markAllReadMutation.isPending,
  };
}
