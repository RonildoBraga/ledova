import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from './apiClient';

const okResponse = (config: InternalAxiosRequestConfig, data: unknown = { valid: true }): AxiosResponse => ({
  status: 200,
  statusText: 'OK',
  data,
  headers: {},
  config,
});

const forbidden = (config: InternalAxiosRequestConfig, detail: string) => {
  const response: AxiosResponse = { status: 403, statusText: 'Forbidden', data: { detail }, headers: {}, config };
  return new AxiosError('Request failed with status code 403', AxiosError.ERR_BAD_REQUEST, config, undefined, response);
};

const calls = (adapter: ReturnType<typeof vi.fn>) =>
  adapter.mock.calls.map(([config]) => [(config as InternalAxiosRequestConfig).method, config.url]);

describe('apiClient authentication transport', () => {
  it('sends browser credentials', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
  });

  it('echoes the csrftoken cookie as X-CSRFToken across origins', () => {
    expect(apiClient.defaults.xsrfCookieName).toBe('csrftoken');
    expect(apiClient.defaults.xsrfHeaderName).toBe('X-CSRFToken');
    expect(apiClient.defaults.withXSRFToken).toBe(true);
  });

  it('does not install a default Authorization header', () => {
    expect(Object.keys(apiClient.defaults.headers.common).map((name) => name.toLowerCase())).not.toContain(
      'authorization',
    );
  });
});

describe('apiClient CSRF retry', () => {
  const originalAdapter = apiClient.defaults.adapter;

  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    apiClient.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
  });

  it('refreshes the csrftoken via auth/verify and replays the request once', async () => {
    let posts = 0;
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
      if (config.method === 'get') return okResponse(config);
      posts += 1;
      if (posts === 1) throw forbidden(config, 'CSRF Failed: CSRF cookie not set.');
      return okResponse(config, { message: 'Password changed successfully.' });
    });
    apiClient.defaults.adapter = adapter;

    const response = await apiClient.post('/api/change-password/', {});

    expect(response.data).toEqual({ message: 'Password changed successfully.' });
    expect(calls(adapter)).toEqual([
      ['post', '/api/change-password/'],
      ['get', '/api/auth/verify/'],
      ['post', '/api/change-password/'],
    ]);
  });

  it('gives up after a single replay', async () => {
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
      if (config.method === 'get') return okResponse(config);
      throw forbidden(config, 'CSRF Failed: CSRF token missing.');
    });
    apiClient.defaults.adapter = adapter;

    await expect(apiClient.post('/api/change-password/', {})).rejects.toMatchObject({
      response: { status: 403, data: { detail: 'CSRF Failed: CSRF token missing.' } },
    });
    expect(calls(adapter)).toEqual([
      ['post', '/api/change-password/'],
      ['get', '/api/auth/verify/'],
      ['post', '/api/change-password/'],
    ]);
  });

  it('does not retry other 403 responses', async () => {
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => {
      throw forbidden(config, 'You do not have permission to perform this action.');
    });
    apiClient.defaults.adapter = adapter;

    await expect(apiClient.post('/api/change-password/', {})).rejects.toMatchObject({ response: { status: 403 } });
    expect(adapter).toHaveBeenCalledTimes(1);
  });
});
