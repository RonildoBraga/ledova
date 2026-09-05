import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getCompanyDocuments,
  uploadCompanyDocument,
  deleteCompanyDocument,
  submitApplication,
  resubmitApplication,
  withdrawApplication,
  CACHE_TIMING,
} from '@ledova/shared';
import type { CompanyDocument, DocumentType } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';
import { useCompanyProfile } from '../../hooks/useCompanyProfile';

export function useCompanyDocuments() {
  const queryClient = useQueryClient();
  const { company, companyUuid, isLoading: isLoadingCompany } = useCompanyProfile();

  const { data: docsData, isLoading: isLoadingDocs } = useQuery({
    queryKey: ['company-documents', companyUuid],
    queryFn: () => getCompanyDocuments(apiClient, companyUuid!),
    enabled: !!companyUuid,
    refetchInterval: CACHE_TIMING.SIGNED_URL_REFETCH_INTERVAL,
  });

  const responseData = docsData?.data;
  const documents: CompanyDocument[] = Array.isArray(responseData) ? responseData : responseData?.results || [];
  const uploadedTypes = new Set(documents.map((d) => d.documentType));

  const uploadMutation = useMutation({
    mutationFn: ({ documentType, name, file }: { documentType: DocumentType; name: string; file: unknown }) =>
      uploadCompanyDocument(apiClient, companyUuid!, { documentType, name, file } as Parameters<
        typeof uploadCompanyDocument
      >[2]),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['company-documents', companyUuid] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (docUuid: string) => {
      console.log('[Delete] Deleting document:', docUuid, 'from company:', companyUuid);
      return deleteCompanyDocument(apiClient, companyUuid!, docUuid);
    },
    onSuccess: () => {
      console.log('[Delete] Success');
      queryClient.invalidateQueries({ queryKey: ['company-documents', companyUuid] });
    },
    onError: (error: unknown) => {
      const err = error as { response?: { status?: number; data?: unknown }; message?: string };
      console.log('[Delete] Error:', err?.response?.status, JSON.stringify(err?.response?.data), err?.message);
    },
  });

  const invalidateCompany = () => {
    queryClient.invalidateQueries({ queryKey: ['company', companyUuid] });
    queryClient.invalidateQueries({ queryKey: ['companies'] });
  };

  // The three application transitions the owner drives; each one's backend refusal (400 detail) reaches the
  // caller through mutateAsync so the screen can show it.
  const submitMutation = useMutation({
    mutationFn: () => submitApplication(apiClient, companyUuid!),
    onSuccess: invalidateCompany,
  });

  const resubmitMutation = useMutation({
    mutationFn: (response: string) => resubmitApplication(apiClient, companyUuid!, { response }),
    onSuccess: invalidateCompany,
  });

  const withdrawMutation = useMutation({
    mutationFn: (reason: string) => withdrawApplication(apiClient, companyUuid!, { reason }),
    onSuccess: invalidateCompany,
  });

  const canEdit = company?.status === 'draft' || company?.status === 'info_required';

  return {
    company,
    companyUuid,
    documents,
    uploadedTypes,
    canEdit,
    isLoading: isLoadingCompany || isLoadingDocs,
    upload: uploadMutation.mutateAsync,
    isUploading: uploadMutation.isPending,
    uploadError: uploadMutation.error,
    deleteDocument: deleteMutation.mutate,
    isDeleting: deleteMutation.isPending,
    submitApplication: submitMutation.mutateAsync,
    isSubmitting: submitMutation.isPending,
    resubmitApplication: resubmitMutation.mutateAsync,
    isResubmitting: resubmitMutation.isPending,
    withdrawApplication: withdrawMutation.mutateAsync,
    isWithdrawing: withdrawMutation.isPending,
  };
}
