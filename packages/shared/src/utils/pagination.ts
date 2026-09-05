import type { PaginatedResponse } from '../types';

/** Next page number for TanStack Query's `getNextPageParam`, read from the response's `next` URL. */
export const getNextPageParam = <T>(lastPage: PaginatedResponse<T> | undefined): number | undefined => {
  if (!lastPage?.next) return undefined;
  const page = new URL(lastPage.next).searchParams.get('page');
  return page ? Number(page) : undefined;
};
