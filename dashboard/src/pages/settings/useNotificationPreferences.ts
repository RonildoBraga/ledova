import { useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getNotificationPreferences, updateNotificationPreferences, CACHE_TIMING } from '@ledova/shared';
import type { UpdateNotificationPreferencesRequest, NotificationPreferences } from '@ledova/shared';
import apiClient from '@services/apiClient';
import { useAuth } from '@hooks/useAuth';

export function useNotificationPreferences() {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();

  const preferencesQuery = useQuery({
    queryKey: ['notificationPreferences'],
    queryFn: () => getNotificationPreferences(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const updateMutation = useMutation({
    mutationFn: (data: UpdateNotificationPreferencesRequest) => updateNotificationPreferences(apiClient, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notificationPreferences'] });
    },
  });

  const preferences: NotificationPreferences | undefined = preferencesQuery.data?.data;

  const toggleTransactionAlerts = useCallback(
    async (value: boolean) => {
      await updateMutation.mutateAsync({ transaction_alerts: value });
    },
    [updateMutation],
  );

  const togglePriceAlerts = useCallback(
    async (value: boolean) => {
      await updateMutation.mutateAsync({ price_alerts: value });
    },
    [updateMutation],
  );

  const toggleMarketing = useCallback(
    async (value: boolean) => {
      await updateMutation.mutateAsync({ marketing: value });
    },
    [updateMutation],
  );

  return {
    transactionAlerts: preferences?.transactionAlerts ?? true,
    priceAlerts: preferences?.priceAlerts ?? false,
    marketing: preferences?.marketing ?? false,
    isLoading: preferencesQuery.isLoading,
    isUpdating: updateMutation.isPending,
    toggleTransactionAlerts,
    togglePriceAlerts,
    toggleMarketing,
  };
}
