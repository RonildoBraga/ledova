import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useSyncExternalStore } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getIdentityVerificationToken, getIdentityVerificationStatus, CACHE_TIMING } from '@ledova/shared';
import { apiClient } from '../services/apiClient';
import { getSessionEpoch, subscribeSession } from '../services/sessionScope';

export function useIdentityVerification(enabled = true) {
  const queryClient = useQueryClient();
  const epoch = useSyncExternalStore(subscribeSession, getSessionEpoch, getSessionEpoch);
  const [, render] = useReducer((value: number) => value + 1, 0);
  const submission = useMemo(() => ({ epoch, justSubmitted: false }), [epoch]);
  const scope = useMemo(
    () => ({
      enabled,
      epoch,
      generation: 0,
      disposed: false,
      launching: false,
      sdkError: null as string | null,
      tokenError: null as Error | null,
      accessToken: null as string | null,
      formUrl: null as string | null,
    }),
    [enabled, epoch],
  );
  const current = useRef(scope);
  current.current = scope;
  const isCurrent = useCallback(
    () => scope.enabled && !scope.disposed && current.current === scope && scope.epoch === getSessionEpoch(),
    [scope],
  );

  useLayoutEffect(() => {
    scope.disposed = false;
    return () => {
      scope.disposed = true;
      scope.generation++;
      scope.accessToken = null;
      scope.formUrl = null;
    };
  }, [scope]);

  const { justSubmitted } = submission;
  const statusQuery = useQuery({
    queryKey: ['identity-verification', 'status'],
    queryFn: async () => {
      const response = await getIdentityVerificationStatus(apiClient);
      return response.data;
    },
    staleTime: CACHE_TIMING.SHORT_STALE_TIME,
    gcTime: CACHE_TIMING.LONG_GC_TIME,
    retry: 1,
    refetchOnWindowFocus: false,
    refetchOnReconnect: true,

    refetchInterval: (query) => {
      if (!justSubmitted) return false;
      const data = query.state.data;
      if (data?.isVerified) return false;
      if (data?.reviewAnswer === 'RED' && !data?.needsRetry) return false;
      return 5000;
    },
  });

  const tokenMutation = useMutation({
    mutationFn: async () => {
      const response = await getIdentityVerificationToken(apiClient);
      return response.data;
    },
  });

  const status = statusQuery.data;
  const isVerified = status?.isVerified ?? false;
  const needsRetry = status?.needsRetry ?? false;
  const hasApplicant = !!status?.applicantId;

  const isPending = !!status && ['pending', 'queued'].includes(status.status ?? '') && !status.isVerified;
  const isOnHold = !!status && status.status === 'onHold' && !status.isVerified;
  const isRejected = !!status && status.reviewAnswer === 'RED' && !status.isVerified && !status.needsRetry;
  const hasSubmitted = !!status && ['pending', 'queued', 'onHold'].includes(status.status ?? '') && !status.isVerified;

  useEffect(() => {
    if (!scope.disposed && submission.epoch === getSessionEpoch() && justSubmitted && (isVerified || isRejected)) {
      submission.justSubmitted = false;
      render();
      queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });
    }
  }, [justSubmitted, isVerified, isRejected, queryClient, scope, submission]);

  const showVerificationForm = isCurrent() && (!!scope.accessToken || !!scope.formUrl);

  const closeFormModal = useCallback(() => {
    if (!isCurrent()) return;
    scope.generation++;
    scope.launching = false;
    scope.accessToken = null;
    scope.formUrl = null;
    render();
  }, [scope, isCurrent]);

  const handleFormComplete = useCallback(() => {
    if (!isCurrent()) return;
    closeFormModal();
    submission.justSubmitted = true;
    render();
  }, [submission, isCurrent, closeFormModal]);

  const launchVerification = useCallback(async () => {
    if (!isCurrent() || scope.launching) return;
    const generation = ++scope.generation;
    const currentLaunch = () => isCurrent() && scope.generation === generation;
    scope.launching = true;
    scope.sdkError = null;
    scope.tokenError = null;
    render();
    try {
      const data = await tokenMutation.mutateAsync();
      if (!currentLaunch()) return;
      queryClient.invalidateQueries({ queryKey: ['identity-verification', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });
      scope.formUrl = data?.formUrl ?? null;
      scope.accessToken = scope.formUrl ? null : (data?.accessToken ?? null);
    } catch (error: unknown) {
      if (!currentLaunch()) return;
      scope.sdkError = error instanceof Error ? error.message : 'Failed to initialize verification';
      scope.tokenError = error instanceof Error ? error : null;
    } finally {
      if (currentLaunch()) {
        scope.launching = false;
        render();
      }
    }
  }, [tokenMutation, queryClient, scope, isCurrent]);

  const resetState = useCallback(() => {
    if (!isCurrent()) return;
    closeFormModal();
    scope.sdkError = null;
    scope.tokenError = null;
    submission.justSubmitted = false;
    render();
  }, [scope, submission, isCurrent, closeFormModal]);

  const clearError = useCallback(() => {
    if (!isCurrent()) return;
    scope.sdkError = null;
    scope.tokenError = null;
    render();
  }, [scope, isCurrent]);

  return {
    status,
    isLoadingStatus: statusQuery.isLoading,
    refetchStatus: statusQuery.refetch,

    isVerified,
    needsRetry,
    hasApplicant,
    isPending,
    isOnHold,
    isRejected,
    hasSubmitted,

    launchVerification,
    isLaunching: scope.launching,

    accessToken: scope.accessToken,
    formUrl: scope.formUrl,
    formSessionEpoch: showVerificationForm ? scope.epoch : null,
    showVerificationForm,
    handleFormComplete,
    closeFormModal,

    justSubmitted,
    sdkError: scope.sdkError,
    clearError,
    tokenError: scope.tokenError,
    resetState,
  };
}
