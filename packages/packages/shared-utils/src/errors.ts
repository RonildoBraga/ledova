import type { UserFriendlyError } from '@ledova/shared-types';

/**
 * Creates a user-friendly error with a clean message for display
 * while preserving the original error for debugging.
 *
 * @param message - The user-friendly message to display
 * @param originalError - The original error for debugging purposes
 * @returns A UserFriendlyError instance
 */
export function createUserFriendlyError(message: string, originalError?: unknown): UserFriendlyError {
  const error = new Error(message) as UserFriendlyError;
  error.isUserFriendly = true;
  error.originalError = originalError;
  return error;
}

/**
 * Extracts a human-readable error message from various error types.
 * Handles axios errors, standard Error objects, strings, and unknown types.
 *
 * @param error - The error to extract a message from
 * @param defaultMessage - Optional default message if no message can be extracted
 * @returns The error message string, or null if no error
 *
 * @example
 * // Axios error
 * getErrorMessage(axiosError) // Returns response.data.message if available
 *
 * // Standard Error
 * getErrorMessage(new Error('Something went wrong')) // Returns 'Something went wrong'
 *
 * // String
 * getErrorMessage('Failed to load') // Returns 'Failed to load'
 *
 * // No error
 * getErrorMessage(null) // Returns null
 */
export function getErrorMessage(error: unknown, defaultMessage = 'An error occurred'): string | null {
  if (!error) return null;

  // Handle string errors directly
  if (typeof error === 'string') return error;

  // Handle axios-style errors with response.data.message
  if (error && typeof error === 'object' && 'response' in error) {
    const axiosError = error as { response?: { data?: { message?: string; detail?: string } } };
    if (axiosError.response?.data?.message) return axiosError.response.data.message;
    if (axiosError.response?.data?.detail) return axiosError.response.data.detail;
  }

  // Handle standard Error objects
  if (error && typeof error === 'object' && 'message' in error) {
    return (error as { message: string }).message;
  }

  return defaultMessage;
}
