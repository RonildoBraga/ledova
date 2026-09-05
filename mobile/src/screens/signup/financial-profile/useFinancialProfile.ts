import { useState, useEffect } from 'react';
import { getFinancialProfiles, createFinancialProfile, updateFinancialProfile, getUserProfiles } from '@ledova/shared';
import { apiClient } from '../../../services/apiClient';
import type { CreateFinancialProfile, FinancialProfileFormState, FormErrors } from '@ledova/shared';

/**
 * Hook for managing financial profile
 *
 * AML/CTF Compliance: Collects source of funds, occupation, and intended use
 * as required by Ledova AML/CTF Program (Part B, Section 16.1, Step 4).
 */
export const useFinancialProfile = () => {
  const [form, setForm] = useState<FinancialProfileFormState>({
    userProfileId: '',
    occupation: '',
    sourceOfFunds: [],
    sourceOfFundsOtherText: '',
    intendedUse: '',
    intendedUseOtherText: '',
  });

  const [errors, setErrors] = useState<FormErrors>({});
  const [generalError, setGeneralError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [existingProfileUuid, setExistingProfileUuid] = useState<string | null>(null);
  const [userProfileId, setUserProfileId] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    setGeneralError('');

    try {
      const profileResponse = await getUserProfiles(apiClient);
      const profileData = profileResponse.data;

      if (profileData && profileData.results && profileData.count > 0) {
        const userProfile = profileData.results[0];
        const profileUuid = userProfile.uuid;
        setUserProfileId(profileUuid);
        setForm((prev) => ({ ...prev, userProfileId: profileUuid }));

        const financialProfileResponse = await getFinancialProfiles(apiClient);
        const financialProfileData = financialProfileResponse.data;

        if (financialProfileData && financialProfileData.results && financialProfileData.count > 0) {
          const existingProfile = financialProfileData.results[0];
          setExistingProfileUuid(existingProfile.uuid);

          setForm({
            userProfileId: profileUuid,
            occupation: existingProfile.occupation || '',
            sourceOfFunds: existingProfile.sourceOfFunds || [],
            sourceOfFundsOtherText: existingProfile.sourceOfFundsOtherText || '',
            intendedUse: existingProfile.intendedUse || '',
            intendedUseOtherText: existingProfile.intendedUseOtherText || '',
          });
        }
      } else {
        setGeneralError('Please complete your user profile first.');
      }
    } catch {
      setGeneralError('Failed to load profile. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const setFieldValue = (field: keyof FinancialProfileFormState, value: string | string[] | number) => {
    setForm((prev) => ({
      ...prev,
      [field]: value,
    }));

    if (errors[field]) {
      const newErrors = { ...errors };
      delete newErrors[field];
      setErrors(newErrors);
    }
    setGeneralError('');
  };

  const toggleSourceOfFunds = (value: string) => {
    const currentSources = form.sourceOfFunds;
    if (currentSources.includes(value)) {
      setFieldValue(
        'sourceOfFunds',
        currentSources.filter((s) => s !== value),
      );
    } else {
      setFieldValue('sourceOfFunds', [...currentSources, value]);
    }
  };

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    // Occupation validation (optional but if provided must be 2-200 chars)
    if (form.occupation && (form.occupation.length < 2 || form.occupation.length > 200)) {
      newErrors.occupation = ['Occupation must be between 2 and 200 characters'];
    }

    // Source of funds "Other" text required if "other" selected
    if (form.sourceOfFunds.includes('other') && !form.sourceOfFundsOtherText?.trim()) {
      newErrors.sourceOfFundsOtherText = ['Please specify your source of funds'];
    }

    // Intended use "Other" text required if "other" selected
    if (form.intendedUse === 'other' && !form.intendedUseOtherText?.trim()) {
      newErrors.intendedUseOtherText = ['Please specify your intended use'];
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (onSuccess: () => void) => {
    if (!validateForm()) {
      return;
    }

    if (!userProfileId) {
      setGeneralError('User profile not found. Please complete your profile first.');
      return;
    }

    setIsSubmitting(true);
    setGeneralError('');

    try {
      const apiPayload: CreateFinancialProfile = {
        occupation: form.occupation || null,
        sourceOfFunds: form.sourceOfFunds,
        sourceOfFundsOtherText: form.sourceOfFundsOtherText || null,
        intendedUse: form.intendedUse || null,
        intendedUseOtherText: form.intendedUseOtherText || null,
      };

      if (existingProfileUuid) {
        await updateFinancialProfile(apiClient, existingProfileUuid, apiPayload);
      } else {
        await createFinancialProfile(apiClient, apiPayload);
      }

      onSuccess();
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: unknown } };
      if (axiosError.response?.data) {
        const errorData = axiosError.response.data;
        if (typeof errorData === 'object' && !Array.isArray(errorData)) {
          setErrors(errorData as FormErrors);

          const firstError = Object.values(errorData).flat()[0];
          if (firstError) {
            setGeneralError(firstError as string);
          }
        } else if (typeof errorData === 'string') {
          setGeneralError(errorData);
        } else {
          setGeneralError('Failed to save profile. Please try again.');
        }
      } else {
        setGeneralError('Network error. Please check your connection.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const retryLoad = () => {
    loadData();
  };

  return {
    form,
    errors,
    generalError,
    isLoading,
    isSubmitting,
    userProfileId,
    setFieldValue,
    toggleSourceOfFunds,
    handleSubmit,
    retryLoad,
  };
};
