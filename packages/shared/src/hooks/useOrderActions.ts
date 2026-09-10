import { useCallback, useEffect, useMemo, useReducer, useRef, useSyncExternalStore } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { OrderActionPurpose, UserPreferences } from '../types';
import { OrderAction } from '../utils/order-action';
import type { OrderActionStore, SavedOrderAction } from '../utils/order-action-storage';
import type { OrderSubmissionOwner } from '../utils/order-submission-storage';
import type { OrderSubmissionSession } from './useOrderSubmissions';
import { useApiClient } from './useApiClient';
import { AUTH_QUERY_KEY } from './useAuth';
import { USER_PREFERENCES_QUERY_KEY, useUserPreferences } from './useUserPreferences';

export function useOrderActions(store: OrderActionStore, session?: OrderSubmissionSession) {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();
  useUserPreferences();
  const [, render] = useReducer((value: number) => value + 1, 0);
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
  const state = useMemo(
    () => ({
      retired: false,
      listGeneration: 0,
      active: null as OrderAction | null,
      pending: [] as SavedOrderAction[],
      loading: false,
      error: null as string | null,
    }),
    [owner, store],
  );
  const currentState = useRef(state);
  currentState.current = state;
  const isCurrent = useCallback(
    () => !state.retired && currentState.current === state && !!owner && boundary.get() === owner,
    [state, owner, boundary],
  );
  const reload = useCallback(async (): Promise<void> => {
    if (!owner || !isCurrent()) return;
    const generation = ++state.listGeneration;
    state.loading = true;
    render();
    try {
      const records = await store.list(owner);
      if (isCurrent() && generation === state.listGeneration) {
        state.pending = records;
        state.error = null;
      }
    } catch {
      if (isCurrent() && generation === state.listGeneration)
        state.error = 'Saved cancellations and changes could not be read. Please try again.';
    } finally {
      if (isCurrent() && generation === state.listGeneration) {
        state.loading = false;
        render();
      }
    }
  }, [owner, isCurrent, state, store]);
  useEffect(() => {
    state.retired = false;
    void reload();
    return () => {
      state.retired = true;
      state.active?.close();
    };
  }, [state, reload]);
  const close = () => {
    state.active?.close();
    state.active = null;
    if (isCurrent()) render();
  };
  const select = (orderUuid: string, purpose: OrderActionPurpose, record: SavedOrderAction | null = null) => {
    if (!isCurrent() || !owner) return null;
    state.active?.close();
    const selection: OrderAction = new OrderAction(
      owner,
      orderUuid,
      purpose,
      {
        apiClient,
        store,
        isCurrent: () => isCurrent() && state.active === selection,
        requestConfig: session?.requestConfig(),
        onRecordsChanged: () => {
          if (isCurrent()) void reload();
        },
        onSettled: (snapshot) => {
          if (isCurrent() && state.active === selection && snapshot.status === 'applied')
            void queryClient.invalidateQueries({ queryKey: ['trading'] });
        },
      },
      record,
    );
    state.active = selection;
    render();
    return selection;
  };
  return {
    owner,
    active: isCurrent() ? state.active : null,
    pending: state.pending,
    error: state.error,
    isLoading: state.loading,
    close,
    refresh: reload,
    open: (orderUuid: string, purpose: OrderActionPurpose) => {
      if (state.active?.orderUuid === orderUuid && state.active.purpose === purpose) return;
      const selection = select(orderUuid, purpose);
      if (selection) void selection.load();
    },
    recover: (record: SavedOrderAction) => {
      if (
        !owner ||
        record.userUuid !== owner.userUuid ||
        record.ownerAccountUuid !== owner.ownerAccountUuid ||
        state.active?.record?.actionId === record.actionId
      )
        return;
      const selection = select(record.orderUuid, record.purpose, record);
      if (selection) void selection.recover();
    },
  };
}
