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

export function hasServiceErrorDetail(error: unknown): boolean {
  if (!error || typeof error !== 'object' || !('response' in error)) return false;
  const data = (error as { response?: { data?: unknown } }).response?.data;
  if (!data || typeof data !== 'object') return false;
  const detail = (data as { detail?: unknown }).detail;
  return typeof detail === 'string' && detail.trim().length > 0;
}

interface FailureShape {
  name?: unknown;
  code?: unknown;
  message?: unknown;
  response?: { status?: unknown } | null;
  config?: { method?: unknown; url?: unknown } | null;
}

function requestPath(url: unknown): string | null {
  if (typeof url !== 'string') return null;
  const path = url.split(/[?#]/, 1).join('').trim();
  return path.length > 0 ? path : null;
}

export function describeFailure(error: unknown): string {
  if (typeof error === 'string') return error.length > 0 ? error : 'empty failure';
  if (!error || typeof error !== 'object') return 'unknown failure';

  const failure = error as FailureShape;
  const request: string[] = [];

  const status = failure.response?.status;
  if (typeof status === 'number') request.push(`status=${status}`);

  if (typeof failure.code === 'string' && failure.code.length > 0) request.push(`code=${failure.code}`);

  const path = requestPath(failure.config?.url);
  if (path) {
    const method = failure.config?.method;
    request.push(
      typeof method === 'string' && method.length > 0 ? `request=${method.toUpperCase()} ${path}` : `request=${path}`,
    );
  }

  if (request.length > 0) return request.join(' ');

  const local: string[] = [];
  if (typeof failure.name === 'string' && failure.name.length > 0) local.push(failure.name);
  if (typeof failure.message === 'string' && failure.message.length > 0) local.push(failure.message);

  return local.length > 0 ? local.join(': ') : 'unknown failure';
}
