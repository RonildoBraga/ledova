import { describe, expect, it } from 'vitest';
import apiClient from './apiClient';

describe('apiClient authentication transport', () => {
  it('sends browser credentials', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
  });

  it('does not install a default Authorization header', () => {
    expect(Object.keys(apiClient.defaults.headers.common).map((name) => name.toLowerCase())).not.toContain(
      'authorization',
    );
  });
});
