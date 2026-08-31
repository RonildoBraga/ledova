import type { PaginatedResponse } from '@ledova/shared-types';

/**
 * Extract the next page number from a paginated API response URL.
 * Returns undefined if there are no more pages.
 *
 * @param nextUrl - The "next" URL from a paginated response, or null if no more pages
 * @returns The next page number, or undefined if no more pages
 *
 * @example
 * const nextPage = getNextPageFromUrl(response.data.next);
 * // nextPage = 2 if next URL is "...?page=2"
 * // nextPage = undefined if next URL is null
 */
export const getNextPageFromUrl = (nextUrl: string | null | undefined): number | undefined => {
  if (!nextUrl) return undefined;
  const url = new URL(nextUrl);
  const page = url.searchParams.get('page');
  return page ? Number(page) : undefined;
};

/**
 * Generic helper to extract the next page number from any paginated response.
 * Designed for use with TanStack Query's useInfiniteQuery getNextPageParam.
 *
 * @param lastPage - The last page response containing a PaginatedResponse in data
 * @returns The next page number, or undefined if no more pages
 *
 * @example
 * // Use with TanStack Query's useInfiniteQuery
 * useInfiniteQuery({
 *   queryKey: ['items'],
 *   queryFn: ({ pageParam = 1 }) => getItems(apiClient, { page: pageParam }),
 *   getNextPageParam: (lastPage) => getNextPageParam(lastPage.data),
 *   initialPageParam: 1,
 * });
 */
export const getNextPageParam = <T>(lastPage: PaginatedResponse<T> | undefined): number | undefined => {
  return getNextPageFromUrl(lastPage?.next);
};
