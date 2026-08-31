import type { QueryClient } from '@tanstack/react-query';

/**
 * Invalidates home dashboard queries (holdings, portfolio snapshots, transactions).
 * Used after wallet mutations and on-ramp completions to keep the home screen fresh.
 */
export function invalidateHomeDashboard(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: ['holdings'] });
  queryClient.invalidateQueries({ queryKey: ['portfolio-snapshots'] });
  queryClient.invalidateQueries({ queryKey: ['home-transactions'] });
}
