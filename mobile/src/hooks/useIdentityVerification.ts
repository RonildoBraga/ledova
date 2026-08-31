import { useState, useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getIdentityVerificationToken, getIdentityVerificationStatus } from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import { apiClient } from '../services/apiClient';

export function useIdentityVerification() {
  const queryClient = useQueryClient();

  // Local state
  const [sdkError, setSdkError] = useState<string | null>(null);
  const [justSubmitted, setJustSubmitted] = useState(false);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [formUrl, setFormUrl] = useState<string | null>(null);

  // --- Queries & mutations ---

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
    // Poll every 5s after submission until verified or rejected
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
        // KYCAID: open hosted form in WebView
        setFormUrl(data.formUrl);
      } else if (data?.accessToken) {
        // Sumsub: open WebSDK in WebView
        setAccessToken(data.accessToken);
      }
    },
  });

  // --- Derived status flags ---

  const status = statusQuery.data;
  const isVerified = status?.isVerified ?? false;
  const needsRetry = status?.needsRetry ?? false;
  const hasApplicant = !!status?.applicantId;

  const isPending = !!status && ['pending', 'queued'].includes(status.status ?? '') && !status.isVerified;
  const isOnHold = !!status && status.status === 'onHold' && !status.isVerified;
  const isRejected = !!status && status.reviewAnswer === 'RED' && !status.isVerified && !status.needsRetry;
  const hasSubmitted = !!status && ['pending', 'queued', 'onHold'].includes(status.status ?? '') && !status.isVerified;

  // When polling resolves the status, stop polling and refresh profile
  useEffect(() => {
    if (justSubmitted && (isVerified || isRejected)) {
      setJustSubmitted(false);
      queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });
    }
  }, [justSubmitted, isVerified, isRejected, queryClient]);

  // --- Form modal ---

  const showVerificationForm = !!accessToken || !!formUrl;

  const handleFormComplete = useCallback(() => {
    setAccessToken(null);
    setFormUrl(null);
    setJustSubmitted(true);
    // refetchInterval on statusQuery handles polling automatically
  }, []);

  const closeFormModal = useCallback(() => {
    setAccessToken(null);
    setFormUrl(null);
  }, []);

  // --- Provider actions ---

  const launchVerification = useCallback(async () => {
    try {
      setSdkError(null);
      await tokenMutation.mutateAsync();
      // accessToken or formUrl is set via tokenMutation.onSuccess → opens modal automatically
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
    // Status
    status,
    isLoadingStatus: statusQuery.isLoading,
    refetchStatus: statusQuery.refetch,

    // Convenience flags
    isVerified,
    needsRetry,
    hasApplicant,
    isPending,
    isOnHold,
    isRejected,
    hasSubmitted,

    // Actions
    launchVerification,
    isLaunching: tokenMutation.isPending,

    // Form modal
    accessToken,
    formUrl,
    showVerificationForm,
    handleFormComplete,
    closeFormModal,

    // State
    justSubmitted,
    sdkError,
    clearError,
    tokenError: tokenMutation.error,
    resetState,
  };
}
