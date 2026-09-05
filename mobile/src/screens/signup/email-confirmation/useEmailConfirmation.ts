import { useState, useEffect } from 'react';
import { verifyEmail, resendVerificationCode } from '@ledova/shared-services';
import { FormErrors } from '@ledova/shared-types';
import { validateEmailConfirmation, formatVerificationToken } from '@ledova/shared-utils';
import { EMAIL_CONFIRMATION_VALIDATION } from '@ledova/shared-constants';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { apiClient } from '../../../services/apiClient';

export const useEmailConfirmation = () => {
  const [email, setEmail] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [generalError, setGeneralError] = useState<string>('');
  const [successMessage, setSuccessMessage] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [isResending, setIsResending] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem('signup_email').then((storedEmail) => {
      if (storedEmail) {
        setEmail(storedEmail);
      }
    });
  }, []);

  const handleVerify = async (onSuccess: () => void) => {
    const validation = validateEmailConfirmation(verificationCode, EMAIL_CONFIRMATION_VALIDATION.TOKEN_LENGTH);

    if (!validation.isValid) {
      setErrors({
        token: [`Please enter a valid ${EMAIL_CONFIRMATION_VALIDATION.TOKEN_LENGTH}-digit verification code`],
      });
      return;
    }

    setIsLoading(true);
    setGeneralError('');
    setErrors({});

    try {
      const response = await verifyEmail(apiClient, {
        email,
        token: formatVerificationToken(verificationCode),
      });

      if (response.data?.tokens && response.data.tokens.length > 0) {
        const token = response.data.tokens[0];
        if (token.accessToken && token.refreshToken) {
          await SecureStore.setItemAsync('accessToken', token.accessToken);
          await SecureStore.setItemAsync('refreshToken', token.refreshToken);
        }
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
          setGeneralError('Invalid verification code. Please try again.');
        }
      } else {
        setGeneralError('Network error. Please check your connection.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleResend = async () => {
    setIsResending(true);
    setSuccessMessage('');
    setGeneralError('');

    try {
      await resendVerificationCode(apiClient, { email });
      setSuccessMessage('Verification code sent! Please check your email.');
      setVerificationCode('');
    } catch {
      setGeneralError('Failed to resend code. Please try again.');
    } finally {
      setIsResending(false);
    }
  };

  return {
    email,
    verificationCode,
    errors,
    generalError,
    successMessage,
    isLoading,
    isResending,
    setVerificationCode,
    handleVerify,
    handleResend,
  };
};
