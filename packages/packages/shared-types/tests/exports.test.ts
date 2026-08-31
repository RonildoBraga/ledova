import type { AssetFilters } from '../src';

describe('shared-types exports', () => {
  it('should export type definitions module', () => {
    const typeExports = require('../src/index');
    expect(typeExports).toBeDefined();
  });

  it('exposes the public compile-time type surface', () => {
    const filters: AssetFilters = { search: 'synthetic', chain: 'ethereum' };
    expect(filters).toEqual({ search: 'synthetic', chain: 'ethereum' });
  });
});
