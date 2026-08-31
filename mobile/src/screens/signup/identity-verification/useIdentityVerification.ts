import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useIdentityVerification as useIdentityVerificationApi } from '../../../hooks/useIdentityVerification';

export const useIdentityVerification = () => {
  const [isContinuing, setIsContinuing] = useState(false);
  const queryClient = useQueryClient();

  const {
    status,
    isLoadingStatus,
    tokenError,
    isVerified,
    hasApplicant,
    refetchStatus,
    isOnHold,
    isRejected,
    needsRetry,
    hasSubmitted,
    launchVerification,
    isLaunching,
    sdkError,
    justSubmitted,
    accessToken,
    formUrl,
    showVerificationForm,
    handleFormComplete,
    closeFormModal,
  } = useIdentityVerificationApi();

  // Display state: combine local justSubmitted with API-derived hasSubmitted
  const showPendingBanner = (justSubmitted || hasSubmitted) && !isVerified && !isRejected;
  const showOnHoldBanner = isOnHold && !justSubmitted;
  const showRejectedBanner = isRejected && !justSubmitted;
  const showRetryBanner = needsRetry && !isVerified && !justSubmitted;
  const showForm = !isVerified && !showPendingBanner && !showRetryBanner;
  const showContinue = isVerified || hasSubmitted || justSubmitted;
  const showSkip = !isVerified && !hasSubmitted && !justSubmitted;

  // Handle continue to next screen — refresh both status and profile caches
  const prepareForNextScreen = async () => {
    setIsContinuing(true);
    try {
      await refetchStatus();
      queryClient.invalidateQueries({ queryKey: ['user', 'profile'] });
      return true;
    } catch {
      return false;
    } finally {
      setIsContinuing(false);
    }
  };

  return {
    // Verification status
    status,
    isLoadingStatus,
    isVerified,

    // Display flags
    showPendingBanner,
    showOnHoldBanner,
    showRejectedBanner,
    showRetryBanner,
    showForm,
    showContinue,
    showSkip,

    // Errors
    tokenError,
    sdkError,

    // Actions
    launchVerification,
    prepareForNextScreen,

    // Loading states
    isLaunching,
    isContinuing,

    // Provider flags
    hasApplicant,

    // Form modal
    accessToken,
    formUrl,
    showVerificationForm,
    handleFormComplete,
    closeFormModal,
  };
};
