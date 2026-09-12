import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { SwapSettlementCrypto, SwapSettlementSelection } from '../types';
import { SwapSettlement } from '../utils/swap-settlement';
import { swapSettlementIdentity } from '../utils/swap-settlement-validation';
import type { SavedSwapSettlement, SwapSettlementStore } from '../utils/swap-settlement-storage';
import type { OrderSubmissionSession } from './useOrderSubmissions';
import { useOrderOwner } from './useOrderOwner';
import { useApiClient } from './useApiClient';

export function useSwapSettlements(
  store: SwapSettlementStore,
  crypto: SwapSettlementCrypto,
  session?: OrderSubmissionSession,
) {
  const apiClient = useApiClient();
  const queryClient = useQueryClient();
  const { owner, boundary } = useOrderOwner(session);
  const [, render] = useReducer((value: number) => value + 1, 0);
  const state = useMemo(
    () => ({
      retired: false,
      listGeneration: 0,
      active: null as SwapSettlement | null,
      pending: [] as SavedSwapSettlement[],
      loading: false,
      error: null as string | null,
    }),
    [owner, store, crypto],
  );
  const latest = useRef(state);
  latest.current = state;
  const isCurrent = useCallback(
    () => !state.retired && latest.current === state && !!owner && boundary.get() === owner,
    [state, owner, boundary],
  );
  const refresh = useCallback(async (): Promise<void> => {
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
        state.error = 'Saved settlements could not be read. Please try again.';
    } finally {
      if (isCurrent() && generation === state.listGeneration) {
        state.loading = false;
        render();
      }
    }
  }, [owner, isCurrent, state, store]);
  useEffect(() => {
    state.retired = false;
    void refresh();
    return () => {
      state.retired = true;
      state.active?.close();
    };
  }, [state, refresh]);
  const close = () => {
    state.active?.close();
    state.active = null;
    if (isCurrent()) render();
  };
  const open = (selection: SwapSettlementSelection, additionalCurrent: () => boolean = () => true) => {
    if (!owner || !isCurrent() || selection.ownerAccountUuid !== owner.ownerAccountUuid || !additionalCurrent())
      return null;
    state.active?.close();
    const active: SwapSettlement = new SwapSettlement(owner, selection, {
      apiClient,
      store,
      crypto,
      requestConfig: session?.requestConfig(),
      isCurrent: () => isCurrent() && state.active === active && additionalCurrent(),
      onRecordsChanged: () => {
        if (isCurrent()) void refresh();
      },
      onUpdated: () => {
        if (isCurrent() && state.active === active) void queryClient.invalidateQueries({ queryKey: ['trading'] });
      },
    });
    state.active = active;
    render();
    void active.load();
    return active;
  };
  const recover = (record: SavedSwapSettlement, additionalCurrent?: () => boolean) => {
    if (!owner || record.userUuid !== owner.userUuid || record.ownerAccountUuid !== owner.ownerAccountUuid) return null;
    return open(swapSettlementIdentity(record), additionalCurrent);
  };
  return {
    owner,
    active: isCurrent() ? state.active : null,
    pending: state.pending,
    isLoading: state.loading,
    error: state.error,
    open,
    recover,
    close,
    refresh,
  };
}
