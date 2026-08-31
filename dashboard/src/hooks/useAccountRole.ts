import { useQuery } from '@tanstack/react-query';
import { CACHE_TIMING } from '@ledova/shared-constants';
import apiClient from '@services/apiClient';

export type AccountRole = 'investor' | 'company' | 'both';

export function useAccountRole() {
  const query = useQuery({
    queryKey: ['userAccounts'],
    queryFn: () => apiClient.get('/api/user-accounts/'),
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
  });

  const accountsData = query.data?.data as { results?: { role?: string }[] } | { role?: string }[] | undefined;
  const account = Array.isArray(accountsData) ? accountsData[0] : accountsData?.results?.[0] || null;
  const role: AccountRole = (account?.role as AccountRole) ?? 'investor';

  return {
    role,
    isCompany: role === 'company' || role === 'both',
    isInvestor: role === 'investor' || role === 'both',
    isLoading: query.isLoading,
  };
}
