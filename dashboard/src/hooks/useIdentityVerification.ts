import { useState, useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getIdentityVerificationToken, getIdentityVerificationStatus, CACHE_TIMING } from '@ledova/shared';
import apiClient from '@services/apiClient';
import snsWebSdk from '@sumsub/websdk';

export function useIdentityVerification() {
  const queryClient = useQueryClient();

  const [sdkError, setSdkError] = useState<string | null>(null);
  const [justSubmitted, setJustSubmitted] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [formUrl, setFormUrl] = useState<string | null>(null);
  const [sdkActive, setSdkActive] = useState(false);

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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['identity-verification', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });
    },
  });

  const status = statusQuery.data;
  const isVerified = status?.isVerified ?? false;
  const needsRetry = status?.needsRetry ?? false;
  const hasApplicant = !!status?.applicantId;

  const isOnHold = !!status && status.status === 'onHold' && !status.isVerified;
  const isRejected = !!status && status.reviewAnswer === 'RED' && !status.isVerified && !status.needsRetry;
  const hasSubmitted = !!status && ['pending', 'queued', 'onHold'].includes(status.status ?? '') && !status.isVerified;

  useEffect(() => {
    if (justSubmitted && (isVerified || isRejected)) {
      setJustSubmitted(false);
      queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });
    }
  }, [justSubmitted, isVerified, isRejected, queryClient]);

  useEffect(() => {
    if (!formUrl) return;
    const handler = (event: MessageEvent) => {
      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        if (data?.event === 'FORM_COMPLETED') {
          handleFormComplete();
        }
      } catch {}
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [formUrl]);

  const showPendingBanner = (justSubmitted || hasSubmitted) && !isVerified && !isRejected;
  const showOnHoldBanner = isOnHold && !justSubmitted;
  const showRejectedBanner = isRejected && !justSubmitted;
  const showRetryBanner = needsRetry && !isVerified && !justSubmitted;
  const showForm = !isVerified && !showPendingBanner && !showRetryBanner;
  const showContinue = isVerified || hasSubmitted || justSubmitted;
  const showSkip = !isVerified && !hasSubmitted && !justSubmitted;

  const launchVerification = useCallback(
    async (containerId: string) => {
      try {
        setSdkError(null);
        setIsLaunching(true);

        const tokenData = await tokenMutation.mutateAsync();

        if (tokenData?.formUrl) {
          setFormUrl(tokenData.formUrl);
          setIsLaunching(false);
          return;
        }

        if (!tokenData?.accessToken) {
          throw new Error('Failed to generate verification token');
        }

        const snsWebSdkInstance = snsWebSdk
          .init(tokenData.accessToken, () => {
            return tokenMutation.mutateAsync().then((newTokenData) => {
              return newTokenData?.accessToken || '';
            });
          })
          .withConf({
            lang: 'en',
            theme: 'dark',
          })
          .on('idCheck.onApplicantSubmitted', () => {
            setJustSubmitted(true);
          })
          .on('idCheck.onError', (error) => {
            console.error('SumSub error:', error);
            const errorMessage = error?.error || 'An error occurred during verification';
            setSdkError(errorMessage);
          })
          .build();

        snsWebSdkInstance.launch(containerId);
        setSdkActive(true);
      } catch (error: unknown) {
        console.error('Failed to launch verification:', error);
        const errorMessage = error instanceof Error ? error.message : 'Failed to start verification';
        setSdkError(errorMessage);
      } finally {
        setIsLaunching(false);
      }
    },
    [tokenMutation],
  );

  const handleFormComplete = useCallback(() => {
    setFormUrl(null);
    setJustSubmitted(true);
  }, []);

  const resetState = useCallback(() => {
    setSdkError(null);
    setJustSubmitted(false);
    setFormUrl(null);
    setSdkActive(false);
  }, []);

  return {
    status,
    isLoadingStatus: statusQuery.isLoading,
    refetchStatus: statusQuery.refetch,

    showPendingBanner,
    showOnHoldBanner,
    showRejectedBanner,
    showRetryBanner,
    showForm,
    showContinue,
    showSkip,

    isVerified,
    hasApplicant,
    sdkActive,

    launchVerification,

    formUrl,

    justSubmitted,
    sdkError,
    isLaunching,
    tokenError: tokenMutation.error,

    resetState,
  };
}
