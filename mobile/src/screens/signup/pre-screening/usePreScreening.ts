import { useState, useEffect, useCallback } from 'react';
import { getUserProfiles, updateUserProfile } from '@ledova/shared';
import type { UpdateUserProfile } from '@ledova/shared';
import { apiClient } from '../../../services/apiClient';

export const usePreScreening = () => {
  const [acknowledgedWholesaleOnly, setAcknowledgedWholesaleOnly] = useState(false);
  const [form, setForm] = useState<UpdateUserProfile>({
    confirmedOver18: false,
    confirmedAustralianResident: false,
    confirmedIndividualAccount: false,
  });

  const [generalError, setGeneralError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [existingProfileUuid, setExistingProfileUuid] = useState<string | null>(null);

  const loadUserProfile = useCallback(async () => {
    setIsLoading(true);
    setGeneralError('');

    try {
      const response = await getUserProfiles(apiClient);
      const profileData = response.data;

      if (profileData && profileData.results && profileData.count > 0) {
        const existingProfile = profileData.results[0];
        setExistingProfileUuid(existingProfile.uuid);

        setForm({
          confirmedOver18: existingProfile.confirmedOver18 || false,
          confirmedAustralianResident: existingProfile.confirmedAustralianResident || false,
          confirmedIndividualAccount: existingProfile.confirmedIndividualAccount || false,
        });
      }
    } catch {
      setGeneralError('Failed to load profile data. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUserProfile();
  }, [loadUserProfile]);

  const setFieldValue = (
    field: 'confirmedOver18' | 'confirmedAustralianResident' | 'confirmedIndividualAccount',
    value: boolean,
  ) => {
    setForm((prev) => ({
      ...prev,
      [field]: value,
    }));
    setGeneralError('');
  };

  const validateForm = (): boolean => {
    if (
      !form.confirmedOver18 ||
      !form.confirmedAustralianResident ||
      !form.confirmedIndividualAccount ||
      !acknowledgedWholesaleOnly
    ) {
      setGeneralError('You must confirm all requirements to continue.');
      return false;
    }
    return true;
  };

  const handleSubmit = async (onSuccess: () => void) => {
    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    setGeneralError('');

    try {
      if (!existingProfileUuid) {
        throw new Error('User profile not found. Please contact support.');
      }

      await updateUserProfile(apiClient, existingProfileUuid, form);

      onSuccess();
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: unknown } };
      if (axiosError.response?.data) {
        const errorData = axiosError.response.data;
        if (typeof errorData === 'string') {
          setGeneralError(errorData);
        } else {
          setGeneralError('Failed to save pre-screening. Please try again.');
        }
      } else {
        setGeneralError('Network error. Please check your connection.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const retryLoad = () => {
    loadUserProfile();
  };

  const isFormValid =
    form.confirmedOver18 &&
    form.confirmedAustralianResident &&
    form.confirmedIndividualAccount &&
    acknowledgedWholesaleOnly;

  const toggleWholesaleOnly = () => {
    setAcknowledgedWholesaleOnly((previous) => !previous);
    setGeneralError('');
  };

  return {
    form,
    acknowledgedWholesaleOnly,
    toggleWholesaleOnly,
    generalError,
    isLoading,
    isSubmitting,
    isFormValid,
    setFieldValue,
    handleSubmit,
    retryLoad,
  };
};
