/** @jest-environment jsdom */
import { renderHook } from '@testing-library/react';
import type { AxiosInstance } from 'axios';
import { createElement } from 'react';
import type { ReactNode } from 'react';

import { ApiClientProvider, useApiClient } from '../../src/hooks/useApiClient';

const client = { defaults: { baseURL: 'https://ledova.test' } } as unknown as AxiosInstance;
const other = { defaults: { baseURL: 'https://other.test' } } as unknown as AxiosInstance;

const wrapWith = (instance: AxiosInstance) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(ApiClientProvider, { client: instance, children });
  };

describe('useApiClient', () => {
  it('hands back the instance the provider was mounted with', () => {
    const { result } = renderHook(() => useApiClient(), { wrapper: wrapWith(client) });

    expect(result.current).toBe(client);
  });

  it('gives each app its own instance rather than a module-level singleton', () => {
    const first = renderHook(() => useApiClient(), { wrapper: wrapWith(client) });
    const second = renderHook(() => useApiClient(), { wrapper: wrapWith(other) });

    expect(first.result.current).toBe(client);
    expect(second.result.current).toBe(other);
  });

  it('refuses rather than returning null when no provider is mounted', () => {
    expect(() => renderHook(() => useApiClient())).toThrow(/outside an ApiClientProvider/);
  });
});
