import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getCompanyDocuments,
  uploadCompanyDocument,
  deleteCompanyDocument,
  submitApplication,
} from '@ledova/shared-services';
import { CACHE_TIMING } from '@ledova/shared-constants';
import type { CompanyDocument, DocumentType } from '@ledova/shared-types';
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

  const submitMutation = useMutation({
    mutationFn: () => submitApplication(apiClient, companyUuid!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company', companyUuid] });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
    },
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
    submitApplication: submitMutation.mutate,
    isSubmitting: submitMutation.isPending,
  };
}
