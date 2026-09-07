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

export interface SignInErrorReading {
  generalError?: string;
  fieldErrors?: Record<string, string[]>;
}

const THROTTLED_WITHOUT_A_WINDOW = 'Too many sign-in attempts. Please wait before trying again.';
const UNRECOGNISED = 'Unable to sign in at the moment. Please try again later.';

function throttleMessage(retryAfterSeconds: number | null): string {
  if (retryAfterSeconds === null || !Number.isFinite(retryAfterSeconds) || retryAfterSeconds <= 0) {
    return THROTTLED_WITHOUT_A_WINDOW;
  }
  const minutes = Math.ceil(retryAfterSeconds / 60);
  if (minutes < 60) {
    return `Too many sign-in attempts. Please try again in about ${minutes} minute${minutes === 1 ? '' : 's'}.`;
  }
  const hours = Math.ceil(minutes / 60);
  return `Too many sign-in attempts. Please try again in about ${hours} hour${hours === 1 ? '' : 's'}.`;
}

function retryAfterOf(response: { headers?: unknown; data?: unknown }): number | null {
  const headers = response.headers;
  if (headers && typeof headers === 'object') {
    const raw =
      (headers as Record<string, unknown>)['retry-after'] ?? (headers as Record<string, unknown>)['Retry-After'];
    const seconds = Number(raw);
    if (Number.isFinite(seconds) && seconds > 0) return seconds;
  }
  const detail = (response.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === 'string') {
    const found = detail.match(/(\d+)\s*seconds?/);
    if (found) return Number(found[1]);
  }
  return null;
}

export function readSignInError(error: unknown): SignInErrorReading {
  const response = (error as { response?: { status?: number; headers?: unknown; data?: unknown } })?.response;
  if (!response || !('data' in response)) return { generalError: UNRECOGNISED };

  if (response.status === 429) return { generalError: throttleMessage(retryAfterOf(response)) };

  const data = response.data;
  if (Array.isArray(data)) return { generalError: data.join(' ') };
  if (typeof data === 'string') return { generalError: data };
  if (!data || typeof data !== 'object') return { generalError: UNRECOGNISED };

  const body = data as Record<string, unknown>;
  if (typeof body.detail === 'string' && body.detail.trim()) return { generalError: body.detail };
  if (typeof body.error === 'string' && body.error.trim()) return { generalError: body.error };

  const fieldErrors = Object.keys(body).some((key) => Array.isArray(body[key]));
  if (fieldErrors) return { fieldErrors: body as Record<string, string[]> };

  return { generalError: UNRECOGNISED };
}
