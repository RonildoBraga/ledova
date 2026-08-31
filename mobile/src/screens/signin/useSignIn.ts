import { useState } from 'react';
import { signin } from '@ledova/shared-services';
import { FormErrors, SigninRequest } from '@ledova/shared-types';
import * as SecureStore from 'expo-secure-store';
import { apiClient, UserFriendlyError } from '../../services/apiClient';
import { notificationsService } from '../../services/notificationsService';
import { useAuth } from '../../hooks/useAuth';

export const useSignIn = () => {
  const { refetch: refetchAuth } = useAuth();

  const [form, setForm] = useState<SigninRequest>({
    email: '',
    password: '',
  });
  const [errors, setErrors] = useState<FormErrors>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const setFieldValue = (field: keyof SigninRequest, value: string) => {
    setForm({
      ...form,
      [field]: value,
    });
    setErrors({});
    setGeneralError(null);
  };

  const togglePassword = () => {
    setShowPassword(!showPassword);
  };

  const validateForm = (): boolean => {
    const newErrors: FormErrors = {};

    if (!form.email.trim()) {
      newErrors.email = ['Email is required'];
    }

    if (!form.password.trim()) {
      newErrors.password = ['Password is required'];
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const performLogin = async (email: string, password: string, onSuccess?: () => void): Promise<boolean> => {
    try {
      const response = await signin(apiClient, { email, password });

      if (response.data?.tokens && Array.isArray(response.data.tokens) && response.data.tokens.length > 0) {
        const token = response.data.tokens[0];

        const accessToken = token?.accessToken;
        const refreshToken = token?.refreshToken;

        if (accessToken) {
          await SecureStore.setItemAsync('accessToken', accessToken);
        }

        if (refreshToken) {
          await SecureStore.setItemAsync('refreshToken', refreshToken);
        }
      }
      await refetchAuth();

      notificationsService.registerToken().catch(() => {});

      if (onSuccess) {
        onSuccess();
      }
      return true;
    } catch (err: unknown) {
      setErrors({});
      setGeneralError(null);

      if (err && typeof err === 'object' && 'isUserFriendly' in err) {
        const userFriendlyError = err as UserFriendlyError;
        setGeneralError(userFriendlyError.message);
        return false;
      }

      const hasResponse = (error: unknown): error is { response: { data: unknown } } => {
        return (
          typeof error === 'object' &&
          error !== null &&
          'response' in error &&
          typeof error.response === 'object' &&
          error.response !== null &&
          'data' in error.response
        );
      };

      if (hasResponse(err)) {
        const responseData = err.response.data;

        if (Array.isArray(responseData)) {
          setGeneralError(responseData.join(' '));
          return false;
        }

        if (typeof responseData === 'string') {
          setGeneralError(responseData);
          return false;
        }

        if (responseData && typeof responseData === 'object' && 'error' in responseData) {
          const errorObj = responseData as { error: string };
          setGeneralError(errorObj.error);
          return false;
        }

        if (typeof responseData === 'object' && responseData !== null) {
          const hasFieldErrors = Object.keys(responseData).some((key) =>
            Array.isArray((responseData as Record<string, unknown>)[key]),
          );

          if (hasFieldErrors) {
            setErrors(responseData as FormErrors);
          } else {
            setGeneralError('Invalid email or password. Please check your credentials and try again.');
          }
          return false;
        }
      }

      setGeneralError('Unable to sign in at the moment. Please try again later.');
      return false;
    }
  };

  const handleSubmit = async (onSuccess?: () => void) => {
    setGeneralError(null);

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);

    try {
      await performLogin(form.email, form.password, onSuccess);
    } finally {
      setIsLoading(false);
    }
  };

  const loginWithCredentials = async (email: string, password: string, onSuccess?: () => void) => {
    setGeneralError(null);
    setIsLoading(true);

    try {
      await performLogin(email, password, onSuccess);
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
    setFieldValue,
    togglePassword,
    handleSubmit,
    loginWithCredentials,
  };
};
