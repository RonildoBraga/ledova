import { useUserPreferences } from './useUserPreferences';

export type AccountRole = 'investor' | 'company' | 'both';

export function useRole() {
  const { selectedAccount, isLoading } = useUserPreferences();

  const role: AccountRole = (selectedAccount as { role?: AccountRole } | null)?.role ?? 'investor';

  return {
    role,
    isInvestor: role === 'investor' || role === 'both',
    isCompany: role === 'company' || role === 'both',
    isLoading,
  };
}
