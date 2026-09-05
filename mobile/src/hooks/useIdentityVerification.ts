import { useState, useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getIdentityVerificationToken, getIdentityVerificationStatus, CACHE_TIMING } from '@ledova/shared';
import { apiClient } from '../services/apiClient';

export function useIdentityVerification() {
  const queryClient = useQueryClient();

  const [sdkError, setSdkError] = useState<string | null>(null);
  const [justSubmitted, setJustSubmitted] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [formUrl, setFormUrl] = useState<string | null>(null);

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
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['identity-verification', 'status'] });
      queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });

      if (data?.formUrl) {
        setFormUrl(data.formUrl);
      } else if (data?.accessToken) {
        setAccessToken(data.accessToken);
      }
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
    if (justSubmitted && (isVerified || isRejected)) {
      setJustSubmitted(false);
      queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });
    }
  }, [justSubmitted, isVerified, isRejected, queryClient]);

  const showVerificationForm = !!accessToken || !!formUrl;

  const handleFormComplete = useCallback(() => {
    setAccessToken(null);
    setFormUrl(null);
    setJustSubmitted(true);
  }, []);

  const closeFormModal = useCallback(() => {
    setAccessToken(null);
    setFormUrl(null);
  }, []);

  const launchVerification = useCallback(async () => {
    try {
      setSdkError(null);
      await tokenMutation.mutateAsync();
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to initialize verification';
      setSdkError(errorMessage);
    }
  }, [tokenMutation]);

  const resetState = useCallback(() => {
    setAccessToken(null);
    setFormUrl(null);
    setSdkError(null);
    setJustSubmitted(false);
  }, []);

  const clearError = useCallback(() => setSdkError(null), []);

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
    isLaunching: tokenMutation.isPending,

    accessToken,
    formUrl,
    showVerificationForm,
    handleFormComplete,
    closeFormModal,

    justSubmitted,
    sdkError,
    clearError,
    tokenError: tokenMutation.error,
    resetState,
  };
}
