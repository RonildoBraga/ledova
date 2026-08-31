import { useState, useEffect } from 'react';
import { verifyEmail, resendVerificationCode } from '@ledova/shared-services';
import { FormErrors } from '@ledova/shared-types';
import { validateEmailConfirmation, formatVerificationToken } from '@ledova/shared-utils';
import { EMAIL_CONFIRMATION_VALIDATION } from '@ledova/shared-constants';
import apiClient from '@services/apiClient';

export const useSignupEmailConfirmation = () => {
  const [email, setEmail] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [generalError, setGeneralError] = useState<string>('');
  const [successMessage, setSuccessMessage] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [isResending, setIsResending] = useState(false);

  useEffect(() => {
    const storedEmail = localStorage.getItem('signup_email');
    if (storedEmail) {
      setEmail(storedEmail);
    }
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
      await verifyEmail(apiClient, {
        email,
        token: formatVerificationToken(verificationCode),
      });

      localStorage.removeItem('signup_email');

      onSuccess();
    } catch (error: unknown) {
      console.error('Email verification failed:', error);
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
      await resendVerificationCode(apiClient);
      setSuccessMessage('Verification code sent! Please check your email.');
      setVerificationCode('');
    } catch (error) {
      console.error('Failed to resend verification code:', error);
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
