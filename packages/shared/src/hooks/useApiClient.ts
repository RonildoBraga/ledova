import type { AxiosInstance } from 'axios';
import { createContext, createElement, useContext } from 'react';
import type { ReactNode } from 'react';

const ApiClientContext = createContext<AxiosInstance | null>(null);

export interface ApiClientProviderProps {
  client: AxiosInstance;
  children: ReactNode;
}

export function ApiClientProvider({ client, children }: ApiClientProviderProps) {
  return createElement(ApiClientContext.Provider, { value: client }, children);
}

export function useApiClient(): AxiosInstance {
  const client = useContext(ApiClientContext);
  if (client === null) {
    throw new Error('useApiClient was called outside an ApiClientProvider. Mount one at the app root.');
  }
  return client;
}
