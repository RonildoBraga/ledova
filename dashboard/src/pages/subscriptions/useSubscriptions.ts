import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CACHE_TIMING,
  createSubscription,
  getSubscription,
  getSubscriptions,
  getWallets,
  submitSubscription,
  withdrawSubscription,
} from '@ledova/shared';
import type { SubscriptionInput } from '@ledova/shared';
import apiClient from '@services/apiClient';

const SUBSCRIPTIONS_KEY = ['subscriptions'];

export function useSubscriptions() {
  const query = useQuery({
    queryKey: SUBSCRIPTIONS_KEY,
    queryFn: () => getSubscriptions(apiClient),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  return {
    subscriptions: query.data?.data?.results ?? [],
    isLoading: query.isLoading,
  };
}

export function useSubscription(uuid: string | undefined) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['subscriptions', uuid],
    queryFn: () => getSubscription(apiClient, uuid!),
    enabled: !!uuid,
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: SUBSCRIPTIONS_KEY });
    queryClient.invalidateQueries({ queryKey: ['subscriptions', uuid] });
  };

  const submit = useMutation({
    mutationFn: () => submitSubscription(apiClient, uuid!),
    onSuccess: refresh,
  });

  const withdraw = useMutation({
    mutationFn: (reason: string) => withdrawSubscription(apiClient, uuid!, reason),
    onSuccess: refresh,
  });

  return {
    subscription: query.data?.data ?? null,
    isLoading: query.isLoading,
    notFound: query.isError,
    submit,
    withdraw,
  };
}

export function useSubscribableWallets() {
  const query = useQuery({
    queryKey: ['wallets', 'base-verified'],
    queryFn: () => getWallets(apiClient, { chain: 'base', verification_status: 'VERIFIED' }),
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
  });

  return {
    wallets: query.data?.data?.results ?? [],
    isLoading: query.isLoading,
  };
}

export function useCreateSubscription(onCreated: (uuid: string) => void) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: SubscriptionInput) => createSubscription(apiClient, input),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: SUBSCRIPTIONS_KEY });
      onCreated(response.data.uuid);
    },
  });
}
