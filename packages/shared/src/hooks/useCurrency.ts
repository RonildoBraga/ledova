import { useQuery } from '@tanstack/react-query';

import { CACHE_TIMING } from '../constants/api';
import { getExchangeRate } from '../services/exchangeRates';
import type { DisplayCurrency } from '../types';
import { formatCurrency } from '../utils/formatting';
import { useApiClient } from './useApiClient';
import { useAuth } from './useAuth';
import { useUserPreferences } from './useUserPreferences';

export function useCurrency() {
  const apiClient = useApiClient();
  const { isAuthenticated } = useAuth();
  const { preferences } = useUserPreferences();
  const displayCurrency: DisplayCurrency = preferences?.displayCurrency ?? 'AUD';
  const query = useQuery({
    queryKey: ['exchangeRate', displayCurrency],
    queryFn: () => getExchangeRate(apiClient, displayCurrency),
    staleTime: CACHE_TIMING.LONG_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
    enabled: isAuthenticated && displayCurrency !== 'USD',
  });
  const rate = displayCurrency === 'USD' ? 1 : parseFloat(query.data?.data?.rate ?? '0') || 0;

  const formatDisplayCurrency = (usdValue?: number | null, decimals: number = 2): string => {
    if (usdValue === undefined || usdValue === null || isNaN(usdValue)) return '—';
    if (displayCurrency === 'USD') {
      return formatCurrency(usdValue, { currency: 'USD', locale: 'en-US', decimals });
    }
    if (!rate) return '—';
    return formatCurrency(usdValue * rate, { currency: displayCurrency, locale: 'en-AU', decimals });
  };

  return {
    displayCurrency,
    exchangeRate: rate,
    formatDisplayCurrency,
    isLoading: query.isLoading,
  };
}
