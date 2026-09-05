import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getCompanies, getCompany, getCompanyStats, updateCompany } from '@ledova/shared';
import type { Company, CompanyStats, CompanyUpdate } from '@ledova/shared';
import { apiClient } from '../services/apiClient';

export function useCompanyProfile() {
  const queryClient = useQueryClient();

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
    refetch: refetchStats,
  } = useQuery<CompanyStats>({
    queryKey: ['company-stats', companyUuid],
    queryFn: () => getCompanyStats(apiClient, companyUuid!).then((res) => res.data),
    enabled: !!companyUuid,
  });

  const updateMutation = useMutation({
    mutationFn: (data: CompanyUpdate) => updateCompany(apiClient, companyUuid!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company'] });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
  });

  const refetch = async () => {
    await Promise.all([refetchCompany(), refetchStats()]);
  };

  return {
    company: company || companiesData?.data?.results?.[0] || null,
    companyUuid,
    stats: stats || null,
    isLoading: isLoadingList || isLoadingCompany || isLoadingStats,
    error: companyError,
    refetch,
    updateCompany: updateMutation.mutateAsync,
    isUpdating: updateMutation.isPending,
  };
}
