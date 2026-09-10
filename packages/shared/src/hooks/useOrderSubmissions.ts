import { useCallback, useEffect, useMemo, useReducer, useRef, useSyncExternalStore } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { AxiosRequestConfig } from 'axios';
import type { CreateOrderRequest, OrderSubmissionSnapshot, UserPreferences, Wallet } from '../types';
import { OrderSubmission } from '../utils/order-submission';
import type {
  OrderSubmissionOwner,
  OrderSubmissionStore,
  SavedOrderSubmission,
} from '../utils/order-submission-storage';
import { useApiClient } from './useApiClient';
import { AUTH_QUERY_KEY } from './useAuth';
import { USER_PREFERENCES_QUERY_KEY, useUserPreferences } from './useUserPreferences';

export interface OrderSubmissionSession {
  getEpoch: () => number;
  subscribe: (listener: () => void) => () => void;
  requestConfig: () => AxiosRequestConfig;
}

export function useOrderSubmissions(store: OrderSubmissionStore, session?: OrderSubmissionSession) {
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
      if (next !== key) {
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
      owner,
      retired: false,
      generation: 0,
      listGeneration: 0,
      active: null as OrderSubmission | null,
      reserved: null as SavedOrderSubmission | null,
      starting: null as Promise<boolean> | null,
      pending: [] as SavedOrderSubmission[],
      loading: false,
      error: null as string | null,
    }),
    [owner, store],
  );
  const currentState = useRef(state);
  currentState.current = state;
  const isCurrent = useCallback(
    () => !state.retired && currentState.current === state && boundary.get() === owner && !!owner,
    [state, boundary, owner],
  );

  const reload = useCallback(async (): Promise<void> => {
    if (!owner || !isCurrent()) return;
    const generation = ++state.listGeneration;
    state.loading = true;
    render();
    try {
      const pending = await store.list(owner);
      if (!isCurrent() || state.listGeneration !== generation) return;
      state.pending = pending;
      state.error = null;
    } catch {
      if (isCurrent() && state.listGeneration === generation)
        state.error = 'Saved orders could not be read. Please try again.';
    } finally {
      if (isCurrent() && state.listGeneration === generation) {
        state.loading = false;
        render();
      }
    }
  }, [owner, state, store, isCurrent]);

  useEffect(() => {
    state.retired = false;
    void reload();
    return () => {
      state.retired = true;
      state.generation++;
      state.active?.close();
    };
  }, [state, reload]);

  const close = () => {
    state.generation++;
    state.active?.close();
    state.active = null;
    state.reserved = null;
    state.starting = null;
    if (isCurrent()) render();
  };

  const select = (record: SavedOrderSubmission): OrderSubmission => {
    state.active?.close();
    const selection: OrderSubmission = new OrderSubmission(record, {
      apiClient,
      store,
      isCurrent: () => isCurrent() && state.active === selection,
      requestConfig: session?.requestConfig(),
      onRecordsChanged: () => {
        void reload();
      },
      onSettled: (snapshot: OrderSubmissionSnapshot) => {
        if (snapshot.status === 'created') void queryClient.invalidateQueries({ queryKey: ['trading'] });
      },
    });
    state.active = selection;
    render();
    return selection;
  };

  const begin = (draft: CreateOrderRequest, wallet: Wallet | null): Promise<boolean> => {
    if (!isCurrent() || !owner) return Promise.resolve(false);
    if (state.starting) return state.starting;
    if (state.active) return Promise.resolve(true);
    if (
      !wallet ||
      wallet.uuid !== draft.walletUuid ||
      wallet.userAccount !== owner.ownerAccountUuid ||
      wallet.address.toLowerCase() !== draft.walletAddress.toLowerCase()
    ) {
      state.error = 'Choose a wallet belonging to the current account.';
      render();
      return Promise.resolve(false);
    }
    const generation = ++state.generation;
    const original = { ...draft };
    state.error = null;
    const pending = (async () => {
      try {
        const retry = state.reserved?.walletUuid === wallet.uuid;
        if (!retry) state.reserved = store.reserve(owner, wallet.uuid);
        const record = await store.persist(state.reserved!, retry);
        if (!isCurrent() || generation !== state.generation) {
          if (isCurrent()) void reload();
          return false;
        }
        const selection = select(record);
        void reload();
        void selection.start(original);
        return true;
      } catch {
        if (isCurrent() && generation === state.generation) {
          state.error = 'The order could not be saved on this device. No signing request was sent.';
          render();
        }
        return false;
      } finally {
        if (state.generation === generation) {
          state.starting = null;
          if (isCurrent()) render();
        }
      }
    })();
    state.starting = pending;
    render();
    return pending;
  };

  const recover = (record: SavedOrderSubmission) => {
    if (
      !owner ||
      !isCurrent() ||
      state.starting ||
      state.active?.record.submissionId === record.submissionId ||
      record.userUuid !== owner.userUuid ||
      record.ownerAccountUuid !== owner.ownerAccountUuid
    )
      return;
    state.generation++;
    const selection = select(record);
    void selection.recover();
  };

  return {
    owner,
    pending: state.pending,
    active: isCurrent() ? state.active : null,
    isStarting: !!state.starting,
    isLoading: state.loading,
    error: state.error,
    begin,
    recover,
    close,
    refresh: reload,
  };
}
