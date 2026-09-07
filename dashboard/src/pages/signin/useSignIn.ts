import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { readSignInError, signin, FormErrors, SigninRequest } from '@ledova/shared';
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

      await queryClient.refetchQueries({ queryKey: AUTH_QUERY_KEY, exact: true });

      if (onSuccess) {
        onSuccess();
      }
    } catch (err: unknown) {
      setErrors({});
      setGeneralError(null);

      if (err && typeof err === 'object' && 'isUserFriendly' in err) {
        const userFriendlyError = err as UserFriendlyError;
        setGeneralError(userFriendlyError.message);
        return;
      }

      const reading = readSignInError(err);
      if (reading.fieldErrors) {
        setErrors(reading.fieldErrors as FormErrors);
        return;
      }
      setGeneralError(reading.generalError ?? null);
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
