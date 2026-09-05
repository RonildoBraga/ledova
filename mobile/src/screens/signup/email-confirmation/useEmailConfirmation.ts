import { useState, useEffect } from 'react';
import {
  verifyEmail,
  resendVerificationCode,
  FormErrors,
  validateEmailConfirmation,
  formatVerificationToken,
  EMAIL_CONFIRMATION_VALIDATION,
} from '@ledova/shared';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiClient } from '../../../services/apiClient';
import { storeTokens } from '../../../services/tokenStorage';

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
          await storeTokens({ accessToken: token.accessToken, refreshToken: token.refreshToken });
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
