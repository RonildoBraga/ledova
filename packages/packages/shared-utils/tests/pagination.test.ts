import { getNextPageParam } from '../src/pagination';

const page = (next: string | null) => ({ count: 30, next, previous: null, results: [] });

describe('getNextPageParam', () => {
  it('reads the page number from the next URL', () => {
    expect(getNextPageParam(page('https://api.example.com/api/assets/?page=2&page_size=10'))).toBe(2);
  });

  it('returns undefined when there is no next page', () => {
    expect(getNextPageParam(page(null))).toBeUndefined();
    expect(getNextPageParam(undefined)).toBeUndefined();
  });

  it('returns undefined when the next URL carries no page parameter', () => {
    expect(getNextPageParam(page('https://api.example.com/api/assets/?page_size=10'))).toBeUndefined();
  });
});
