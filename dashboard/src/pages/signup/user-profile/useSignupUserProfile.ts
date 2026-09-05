import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  getUserProfiles,
  updateUserProfile,
  FormErrors,
  UserProfileFormValidation,
  UserProfileFormData,
  validateUserProfileField,
  isValidFullName,
  isValidPhoneFormat,
  formatPhoneForDisplay,
  cleanPhoneNumber,
  COUNTRIES,
} from '@ledova/shared';
import type { CountryData } from '@ledova/shared';
import apiClient from '@services/apiClient';

const validateUserProfile = (form: UserProfileFormData): UserProfileFormValidation => {
  const fullNameValidation = validateUserProfileField.fullName(form.fullName);
  const phoneNumberValidation = validateUserProfileField.phoneNumber(form.phoneNumber);
  const residentialAddressValidation = validateUserProfileField.residentialAddress(form.residentialAddress);

  const fullName = {
    isValid: fullNameValidation.isValid,
    isEmpty: form.fullName.trim().length === 0,
    hasValidFormat: isValidFullName(form.fullName),
  };

  const phoneNumber = {
    isValid: phoneNumberValidation.isValid,
    isEmpty: form.phoneNumber.trim().length === 0,
    hasValidFormat: isValidPhoneFormat(form.phoneNumber),
  };

  const residentialAddress = {
    isValid: residentialAddressValidation.isValid,
    isEmpty: form.residentialAddress.trim().length === 0,
    isTooShort: form.residentialAddress.trim().length > 0 && !residentialAddressValidation.isValid,
  };

  return {
    fullName,
    residentialAddress,
    phoneNumber,
    isFormValid: fullName.isValid && residentialAddress.isValid && phoneNumber.isValid,
  };
};

export const useSignupUserProfile = () => {
  const [form, setForm] = useState<UserProfileFormData>({
    fullName: '',
    dateOfBirth: '',
    residentialAddress: '',
    phoneCountryCode: COUNTRIES[0].phoneCode, // Default to Australia's phone code
    phoneNumber: '',
  });

  const [errors, setErrors] = useState<FormErrors>({});
  const [generalError, setGeneralError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [existingProfileUuid, setExistingProfileUuid] = useState<string | null>(null);
  const [selectedCountry, setSelectedCountry] = useState<CountryData>(COUNTRIES[0]); // Default to Australia

  const formValidation = useMemo(() => {
    return validateUserProfile(form);
  }, [form]);

  const loadUserProfile = useCallback(async () => {
    setIsLoading(true);
    setGeneralError('');

    try {
      const response = await getUserProfiles(apiClient);
      const profileData = response.data;

      if (profileData && profileData.results && profileData.count > 0) {
        const existingProfile = profileData.results[0];
        setExistingProfileUuid(existingProfile.uuid);

        // Set selected country from existing phone country code
        if (existingProfile.phoneCountryCode) {
          const detectedCountry = COUNTRIES.find((c) => c.phoneCode === existingProfile.phoneCountryCode);
          if (detectedCountry) {
            setSelectedCountry(detectedCountry);
          }
        }

        // Format existing phone number for display
        let formattedPhoneNumber = existingProfile.phoneNumber || '';
        if (existingProfile.phoneNumber && existingProfile.phoneCountryCode) {
          const country = COUNTRIES.find((c) => c.phoneCode === existingProfile.phoneCountryCode) || selectedCountry;
          formattedPhoneNumber = formatPhoneForDisplay(existingProfile.phoneNumber, country);
        }

        setForm({
          fullName: existingProfile.fullName || '',
          dateOfBirth: existingProfile.dateOfBirth || '',
          residentialAddress: existingProfile.residentialAddress || '',
          phoneCountryCode: existingProfile.phoneCountryCode || COUNTRIES[0].phoneCode,
          phoneNumber: formattedPhoneNumber,
        });
      }
    } catch (error) {
      console.error('Failed to load profile data:', error);
      setGeneralError('Failed to load profile data. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [selectedCountry]);

  useEffect(() => {
    loadUserProfile();
  }, [loadUserProfile]);

  const setFieldValue = (field: keyof UserProfileFormData, value: string) => {
    let processedValue = value;

    if (field === 'phoneNumber') {
      // Apply country-specific formatting for display
      const cleanValue = cleanPhoneNumber(value);
      processedValue = formatPhoneForDisplay(cleanValue, selectedCountry);
    }

    setForm((prev) => ({
      ...prev,
      [field]: processedValue,
    }));

    if (errors[field]) {
      const newErrors = { ...errors };
      delete newErrors[field];
      setErrors(newErrors);
    }
    setGeneralError('');
  };

  const handleCountryChange = (country: CountryData) => {
    setSelectedCountry(country);

    // Update form with new country code and reformat phone number
    setForm((prev) => {
      const cleanNumber = prev.phoneNumber ? cleanPhoneNumber(prev.phoneNumber) : '';
      const formattedNumber = cleanNumber ? formatPhoneForDisplay(cleanNumber, country) : '';

      return {
        ...prev,
        phoneCountryCode: country.phoneCode,
        phoneNumber: formattedNumber,
      };
    });

    // Clear any phone number errors when country changes
    if (errors.phoneNumber || errors.phoneCountryCode) {
      const newErrors = { ...errors };
      delete newErrors.phoneNumber;
      delete newErrors.phoneCountryCode;
      setErrors(newErrors);
    }
    setGeneralError('');
  };

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    if (!form.fullName.trim()) {
      newErrors.fullName = ['Full name is required'];
    }

    if (!form.dateOfBirth.trim()) {
      newErrors.dateOfBirth = ['Date of birth is required'];
    }

    if (!form.residentialAddress.trim()) {
      newErrors.residentialAddress = ['Residential address is required'];
    }

    if (!form.phoneNumber.trim()) {
      newErrors.phoneNumber = ['Phone number is required'];
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
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

      const formattedData = {
        fullName: form.fullName.trim(),
        dateOfBirth: form.dateOfBirth.trim(),
        phoneCountryCode: selectedCountry.phoneCode,
        phoneNumber: cleanPhoneNumber(form.phoneNumber),
        residentialAddress: form.residentialAddress.trim(),
      };

      await updateUserProfile(apiClient, existingProfileUuid, formattedData);

      onSuccess();
    } catch (error: unknown) {
      console.error('User profile update failed:', error);
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
    loadUserProfile();
  };

  return {
    form,
    errors,
    generalError,
    isLoading,
    isSubmitting,
    existingProfileUuid,
    formValidation,
    selectedCountry,
    countries: COUNTRIES,
    setFieldValue,
    handleCountryChange,
    handleSubmit,
    retryLoad,
  };
};
