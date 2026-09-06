import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CACHE_TIMING,
  createOffering,
  deleteOffering,
  getCompanyTokens,
  getOfferings,
  getOfferingSubscriptions,
  submitOffering,
  updateOffering,
  withdrawOffering,
} from '@ledova/shared';
import type { OfferingInput } from '@ledova/shared';
import apiClient from '@services/apiClient';

const OFFERINGS_KEY = ['offerings'];

export function useOfferings() {
  const queryClient = useQueryClient();

  const offeringsQuery = useQuery({
    queryKey: OFFERINGS_KEY,
    queryFn: () => getOfferings(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const tokensQuery = useQuery({
    queryKey: ['company-tokens'],
    queryFn: () => getCompanyTokens(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: OFFERINGS_KEY });

  return {
    offerings: offeringsQuery.data?.data?.results ?? [],
    tokens: (tokensQuery.data?.data?.results ?? []).filter((token) => token.status === 'deployed'),
    isLoading: offeringsQuery.isLoading || tokensQuery.isLoading,
    refresh,
  };
}

export function useOfferingSubscriptions(uuid: string | undefined) {
  const query = useQuery({
    queryKey: ['offering-subscriptions', uuid],
    queryFn: () => getOfferingSubscriptions(apiClient, uuid!),
    enabled: !!uuid,
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  return { subscriptions: query.data?.data?.results ?? [], isLoading: query.isLoading };
}

export function useOfferingActions(onSettled: () => void) {
  const create = useMutation({
    mutationFn: (data: OfferingInput) => createOffering(apiClient, data),
    onSuccess: onSettled,
  });

  const update = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: Partial<OfferingInput> }) =>
      updateOffering(apiClient, uuid, data),
    onSuccess: onSettled,
  });

  const submit = useMutation({
    mutationFn: (uuid: string) => submitOffering(apiClient, uuid),
    onSuccess: onSettled,
  });

  const withdraw = useMutation({
    mutationFn: ({ uuid, reason }: { uuid: string; reason: string }) => withdrawOffering(apiClient, uuid, reason),
    onSuccess: onSettled,
  });

  const remove = useMutation({
    mutationFn: (uuid: string) => deleteOffering(apiClient, uuid),
    onSuccess: onSettled,
  });

  return { create, update, submit, withdraw, remove };
}
