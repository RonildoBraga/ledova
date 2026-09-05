import type { UserFriendlyError } from '../types';

export function createUserFriendlyError(message: string, originalError?: unknown): UserFriendlyError {
  const error = new Error(message) as UserFriendlyError;
  error.isUserFriendly = true;
  error.originalError = originalError;
  return error;
}

export function getErrorMessage(error: unknown, defaultMessage = 'An error occurred'): string | null {
  if (!error) return null;

  if (typeof error === 'string') return error;

  if (error && typeof error === 'object' && 'response' in error) {
    const axiosError = error as { response?: { data?: { message?: string; detail?: string } } };
    if (axiosError.response?.data?.message) return axiosError.response.data.message;
    if (axiosError.response?.data?.detail) return axiosError.response.data.detail;
  }

  if (error && typeof error === 'object' && 'message' in error) {
    return (error as { message: string }).message;
  }

  return defaultMessage;
}
