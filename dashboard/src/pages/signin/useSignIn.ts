import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { signin } from '@ledova/shared-services';
import { FormErrors, SigninRequest } from '@ledova/shared-types';
import apiClient, { UserFriendlyError } from '@services/apiClient';
import { AUTH_QUERY_KEY } from '@hooks/useAuth';

export const useSignIn = () => {
  const queryClient = useQueryClient();
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

  const handleSubmit = async (onSuccess?: () => void) => {
    setGeneralError(null);

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);

    try {
      await signin(apiClient, form);

      // This ensures the auth state is properly initialized before navigation
      await queryClient.refetchQueries({ queryKey: AUTH_QUERY_KEY, exact: true });

      if (onSuccess) {
        onSuccess();
      }
    } catch (err: unknown) {
      console.error('❌ Sign-in error:', err);
      setErrors({});
      setGeneralError(null);

      // Check for user-friendly errors first
      if (err && typeof err === 'object' && 'isUserFriendly' in err) {
        const userFriendlyError = err as UserFriendlyError;
        setGeneralError(userFriendlyError.message);
        return;
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
          return;
        }

        if (typeof responseData === 'string') {
          setGeneralError(responseData);
          return;
        }

        if (responseData && typeof responseData === 'object' && 'error' in responseData) {
          const errorObj = responseData as { error: string };
          setGeneralError(errorObj.error);
          return;
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
          return;
        }
      }

      setGeneralError('Unable to sign in at the moment. Please try again later.');
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
  };
};
