import { useQuery } from '@tanstack/react-query';
import { getCompanies, getCompany, getCompanyStats } from '@ledova/shared';
import type { Company, CompanyListItem, CompanyStats } from '@ledova/shared';
import apiClient from '@services/apiClient';

export type CompanyView = CompanyListItem & Partial<Company>;

export function useCompany() {
  const { data: companiesData, isLoading: isLoadingList } = useQuery({
    queryKey: ['companies'],
    queryFn: () => getCompanies(apiClient),
  });

  const companyUuid = companiesData?.data?.results?.[0]?.uuid;

  const {
    data: company,
    isLoading: isLoadingCompany,
    error: companyError,
    refetch: refetchCompany,
  } = useQuery<Company>({
    queryKey: ['company', companyUuid],
    queryFn: () => getCompany(apiClient, companyUuid!).then((res) => res.data),
    enabled: !!companyUuid,
  });

  const {
    data: stats,
    isLoading: isLoadingStats,
    error: statsError,
    refetch: refetchStats,
  } = useQuery<CompanyStats>({
    queryKey: ['company-stats', companyUuid],
    queryFn: () => getCompanyStats(apiClient, companyUuid!).then((res) => res.data),
    enabled: !!companyUuid,
  });

  const companyView: CompanyView | null = company || companiesData?.data?.results?.[0] || null;

  return {
    company: companyView,
    companyUuid,
    stats: stats || null,
    isLoading: isLoadingList || isLoadingCompany || isLoadingStats,
    error: companyError || statsError,
    refetch: () => {
      refetchCompany();
      refetchStats();
    },
  };
}
