import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getCompanyTokens,
  getCompanyToken,
  deployCompanyToken,
  pauseCompanyToken,
  unpauseCompanyToken,
  getCompanyTokenHolders,
  downloadTokenRegister,
  getCompanyTokenIssuances,
  getCapitalIncreases,
  getShareIssuanceRequests,
  createCompanyToken,
  createCapitalIncrease,
  submitCapitalIncrease,
} from '@ledova/shared';
import type { TokenCreate, CapitalIncreaseCreate } from '@ledova/shared';
import apiClient from '@services/apiClient';

export function useTokensList() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['tokens', page, search, statusFilter],
    queryFn: () =>
      getCompanyTokens(apiClient, {
        page,
        page_size: 10,
        ...(statusFilter ? { status: statusFilter } : {}),
      }),
  });

  const tokens = data?.data?.results || [];
  const totalCount = data?.data?.count || 0;
  const totalPages = Math.ceil(totalCount / 10);

  const createMutation = useMutation({
    mutationFn: (tokenData: TokenCreate) => createCompanyToken(apiClient, tokenData),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tokens'] });
      setIsCreateModalOpen(false);
    },
  });

  return {
    tokens,
    totalCount,
    page,
    totalPages,
    search,
    statusFilter,
    isLoading,
    error,
    isCreateModalOpen,
    setPage,
    setSearch,
    setStatusFilter,
    setIsCreateModalOpen,
    createToken: createMutation.mutateAsync,
    isCreating: createMutation.isPending,
    createError: createMutation.error,
    resetCreateError: createMutation.reset,
  };
}

function saveCsv(data: Blob, filename: string) {
  const url = URL.createObjectURL(data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function useTokenDetail(uuid: string) {
  const [showCapitalIncreaseForm, setShowCapitalIncreaseForm] = useState(false);
  const queryClient = useQueryClient();

  const {
    data: tokenResponse,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['token', uuid],
    queryFn: () => getCompanyToken(apiClient, uuid),
    enabled: !!uuid,
  });

  const token = tokenResponse?.data;

  const { data: holdersResponse, isLoading: isLoadingHolders } = useQuery({
    queryKey: ['token', uuid, 'holders'],
    queryFn: () => getCompanyTokenHolders(apiClient, uuid),
    enabled: !!uuid,
  });

  const { data: issuancesResponse, isLoading: isLoadingIssuances } = useQuery({
    queryKey: ['token', uuid, 'issuances'],
    queryFn: () => getCompanyTokenIssuances(apiClient, uuid),
    enabled: !!uuid,
  });

  const { data: capitalIncreasesResponse, isLoading: isLoadingCapitalIncreases } = useQuery({
    queryKey: ['token', uuid, 'capital-increases'],
    queryFn: () => getCapitalIncreases(apiClient, { token: uuid }),
    enabled: !!uuid,
  });

  const { data: issuanceRequestsResponse, isLoading: isLoadingIssuanceRequests } = useQuery({
    queryKey: ['token', uuid, 'issuance-requests'],
    queryFn: () => getShareIssuanceRequests(apiClient, { token: uuid }),
    enabled: !!uuid,
  });

  const invalidateToken = () => {
    queryClient.invalidateQueries({ queryKey: ['token', uuid] });
    queryClient.invalidateQueries({ queryKey: ['tokens'] });
  };

  const deployMutation = useMutation({
    mutationFn: () => deployCompanyToken(apiClient, uuid),
    onSuccess: invalidateToken,
  });

  const pauseMutation = useMutation({
    mutationFn: () => pauseCompanyToken(apiClient, uuid),
    onSuccess: invalidateToken,
  });

  const unpauseMutation = useMutation({
    mutationFn: () => unpauseCompanyToken(apiClient, uuid),
    onSuccess: invalidateToken,
  });

  const registerMutation = useMutation({
    mutationFn: async () => {
      const response = await downloadTokenRegister(apiClient, uuid);
      saveCsv(response.data, `register-${token?.symbol ?? uuid}.csv`);
    },
  });

  const createCapitalIncreaseMutation = useMutation({
    mutationFn: (data: CapitalIncreaseCreate) => createCapitalIncrease(apiClient, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['token', uuid, 'capital-increases'] });
      setShowCapitalIncreaseForm(false);
    },
  });

  const submitCapitalIncreaseMutation = useMutation({
    mutationFn: (ciUuid: string) => submitCapitalIncrease(apiClient, ciUuid),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['token', uuid, 'capital-increases'] }),
  });

  const holders = holdersResponse?.data;
  const issuances = issuancesResponse?.data;
  const capitalIncreases = capitalIncreasesResponse?.data;

  return {
    token,
    isLoading,
    error,
    downloadRegister: registerMutation.mutateAsync,
    isDownloadingRegister: registerMutation.isPending,
    registerError: registerMutation.error,
    holders: holders?.holders || [],
    totalHolders: holders?.totalHolders || 0,
    isLoadingHolders,
    issuances: issuances?.results || [],
    issuanceCount: issuances?.count || 0,
    isLoadingIssuances,
    capitalIncreases: capitalIncreases?.results || [],
    capitalIncreaseCount: capitalIncreases?.count || 0,
    issuanceRequests: issuanceRequestsResponse?.data?.results || [],
    issuanceRequestCount: issuanceRequestsResponse?.data?.count || 0,
    isLoadingIssuanceRequests,
    isLoadingCapitalIncreases,
    showCapitalIncreaseForm,
    setShowCapitalIncreaseForm,
    deploy: deployMutation.mutateAsync,
    isDeploying: deployMutation.isPending,
    pause: pauseMutation.mutateAsync,
    isPausing: pauseMutation.isPending,
    unpause: unpauseMutation.mutateAsync,
    isUnpausing: unpauseMutation.isPending,
    createCapitalIncrease: createCapitalIncreaseMutation.mutateAsync,
    isCreatingCapitalIncrease: createCapitalIncreaseMutation.isPending,
    submitCapitalIncrease: submitCapitalIncreaseMutation.mutateAsync,
    isSubmittingCapitalIncrease: submitCapitalIncreaseMutation.isPending,
  };
}
