import { useMemo, useSyncExternalStore } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { UserPreferences } from '../types';
import type { OrderSubmissionOwner } from '../utils/order-submission-storage';
import type { OrderSubmissionSession } from './useOrderSubmissions';
import { AUTH_QUERY_KEY } from './useAuth';
import { USER_PREFERENCES_QUERY_KEY, useUserPreferences } from './useUserPreferences';

export function useOrderOwner(session?: OrderSubmissionSession) {
  const queryClient = useQueryClient();
  useUserPreferences();
  const boundary = useMemo(() => {
    let key: string | null = null;
    let value: OrderSubmissionOwner | null = null;
    const get = (): OrderSubmissionOwner | null => {
      const auth = queryClient.getQueryData<{ data: { valid: boolean } }>(AUTH_QUERY_KEY);
      const preferences = queryClient.getQueryData<{ data: UserPreferences }>(USER_PREFERENCES_QUERY_KEY)?.data;
      const authorized = queryClient.getQueryState(AUTH_QUERY_KEY)?.status === 'success' && auth?.data.valid;
      const next =
        authorized && preferences?.userProfile && preferences.selectedAccount
          ? `${preferences.userProfile}/${preferences.selectedAccount.uuid}/${session?.getEpoch() ?? 0}`
          : null;
      if (key !== next) {
        key = next;
        value =
          next && preferences?.selectedAccount
            ? { userUuid: preferences.userProfile, ownerAccountUuid: preferences.selectedAccount.uuid }
            : null;
      }
      return value;
    };
    return {
      get,
      subscribe: (listener: () => void) => {
        const changed = () => {
          get();
          listener();
        };
        const unsubscribeQuery = queryClient.getQueryCache().subscribe(changed);
        const unsubscribeSession = session?.subscribe(changed);
        return () => {
          unsubscribeQuery();
          unsubscribeSession?.();
        };
      },
    };
  }, [queryClient, session]);
  const owner = useSyncExternalStore(boundary.subscribe, boundary.get, boundary.get);
  return { owner, boundary };
}
