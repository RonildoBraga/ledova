import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getCompanyTokens,
  getCompanyToken,
  deployCompanyToken,
  pauseCompanyToken,
  unpauseCompanyToken,
  getCompanyTokenHolders,
  getCompanyTokenIssuances,
  getCapitalIncreases,
  createCompanyToken,
  createCapitalIncrease,
  submitCapitalIncrease,
} from '@ledova/shared';
import type { TokenCreate, CapitalIncreaseCreate, TokenTabType } from '@ledova/shared';
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

export function useTokenDetail(uuid: string) {
  const [activeTab, setActiveTab] = useState<TokenTabType>('overview');
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
    enabled: !!uuid && activeTab === 'shareholders',
  });

  const { data: issuancesResponse, isLoading: isLoadingIssuances } = useQuery({
    queryKey: ['token', uuid, 'issuances'],
    queryFn: () => getCompanyTokenIssuances(apiClient, uuid),
    enabled: !!uuid && activeTab === 'issuances',
  });

  const { data: capitalIncreasesResponse, isLoading: isLoadingCapitalIncreases } = useQuery({
    queryKey: ['token', uuid, 'capital-increases'],
    queryFn: () => getCapitalIncreases(apiClient, { token: uuid }),
    enabled: !!uuid && (activeTab === 'capital-increases' || activeTab === 'shares'),
  });

  const deployMutation = useMutation({
    mutationFn: () => deployCompanyToken(apiClient, uuid),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['token', uuid] }),
  });

  const pauseMutation = useMutation({
    mutationFn: () => pauseCompanyToken(apiClient, uuid),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['token', uuid] }),
  });

  const unpauseMutation = useMutation({
    mutationFn: () => unpauseCompanyToken(apiClient, uuid),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['token', uuid] }),
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

  const refetchTab = useCallback(() => {
    if (activeTab === 'shareholders') queryClient.invalidateQueries({ queryKey: ['token', uuid, 'holders'] });
    if (activeTab === 'issuances') queryClient.invalidateQueries({ queryKey: ['token', uuid, 'issuances'] });
    if (activeTab === 'capital-increases')
      queryClient.invalidateQueries({ queryKey: ['token', uuid, 'capital-increases'] });
  }, [activeTab, uuid, queryClient]);

  const holders = holdersResponse?.data;
  const issuances = issuancesResponse?.data;
  const capitalIncreases = capitalIncreasesResponse?.data;

  return {
    token,
    isLoading,
    error,
    activeTab,
    setActiveTab,
    holders: holders?.holders || [],
    totalHolders: holders?.totalHolders || 0,
    isLoadingHolders,
    issuances: issuances?.results || [],
    issuanceCount: issuances?.count || 0,
    isLoadingIssuances,
    capitalIncreases: capitalIncreases?.results || [],
    capitalIncreaseCount: capitalIncreases?.count || 0,
    isLoadingCapitalIncreases,
    showCapitalIncreaseForm,
    setShowCapitalIncreaseForm,
    deploy: deployMutation.mutateAsync,
    isDeploying: deployMutation.isPending,
    pause: pauseMutation.mutateAsync,
    unpause: unpauseMutation.mutateAsync,
    createCapitalIncrease: createCapitalIncreaseMutation.mutateAsync,
    submitCapitalIncrease: submitCapitalIncreaseMutation.mutateAsync,
    refetchTab,
  };
}
