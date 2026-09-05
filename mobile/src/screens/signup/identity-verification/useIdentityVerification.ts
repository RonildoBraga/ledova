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

  const showPendingBanner = (justSubmitted || hasSubmitted) && !isVerified && !isRejected;
  const showOnHoldBanner = isOnHold && !justSubmitted;
  const showRejectedBanner = isRejected && !justSubmitted;
  const showRetryBanner = needsRetry && !isVerified && !justSubmitted;
  const showForm = !isVerified && !showPendingBanner && !showRetryBanner;
  const showContinue = isVerified || hasSubmitted || justSubmitted;
  const showSkip = !isVerified && !hasSubmitted && !justSubmitted;

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
    status,
    isLoadingStatus,
    isVerified,

    showPendingBanner,
    showOnHoldBanner,
    showRejectedBanner,
    showRetryBanner,
    showForm,
    showContinue,
    showSkip,

    tokenError,
    sdkError,

    launchVerification,
    prepareForNextScreen,

    isLaunching,
    isContinuing,

    hasApplicant,

    accessToken,
    formUrl,
    showVerificationForm,
    handleFormComplete,
    closeFormModal,
  };
};
