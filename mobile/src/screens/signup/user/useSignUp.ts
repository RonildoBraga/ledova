import { useState, useMemo } from 'react';
import {
  signup,
  FormErrors,
  SignupRequest,
  PASSWORD_VALIDATION,
  isNumericOnly,
  validatePassword,
} from '@ledova/shared';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiClient } from '../../../services/apiClient';

export const useSignUp = () => {
  const [form, setForm] = useState<SignupRequest>({
    email: '',
    password: '',
    passwordConfirm: '',
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [generalError, setGeneralError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const passwordValidation = useMemo(() => {
    if (!form.password) {
      return {
        isValid: true,
        lengthValid: true,
        notNumeric: true,
      };
    }
    return validatePassword(form.password, PASSWORD_VALIDATION.MIN_LENGTH);
  }, [form.password]);

  const setFieldValue = (field: keyof SignupRequest, value: string) => {
    setForm((prev) => ({
      ...prev,
      [field]: value,
      ...(field === 'password' ? { passwordConfirm: value } : {}),
    }));
    setErrors({});
    setGeneralError('');
  };

  const togglePassword = () => {
    setShowPassword(!showPassword);
  };

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    if (!form.email) {
      newErrors.email = ['Email is required'];
    }

    if (form.password.length < PASSWORD_VALIDATION.MIN_LENGTH) {
      newErrors.password = [`Password must be at least ${PASSWORD_VALIDATION.MIN_LENGTH} characters long`];
    }

    if (isNumericOnly(form.password)) {
      newErrors.password = [...(newErrors.password || []), 'Password cannot be entirely numeric'];
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (onSuccess: () => void) => {
    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    setGeneralError('');

    try {
      await signup(apiClient, {
        ...form,
        passwordConfirm: form.password,
      });

      await AsyncStorage.setItem('signup_email', form.email);

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
          setGeneralError('Failed to create account. Please try again.');
        }
      } else {
        setGeneralError('Network error. Please check your connection.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return {
    form,
    errors,
    generalError,
    isLoading,
    showPassword,
    passwordValidation,
    setFieldValue,
    togglePassword,
    handleSubmit,
  };
};
