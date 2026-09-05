import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '@services/apiClient';
import {
  deleteDocument,
  getDocument,
  listDocuments,
  uploadDocument,
  type UploadDocumentInput,
} from '@services/documents';
import type { Document } from '../types/document';

const DOCUMENTS_KEY = ['documents'] as const;
const documentKey = (uuid: string) => ['document', uuid] as const;

export function useDocuments() {
  return useQuery({
    queryKey: DOCUMENTS_KEY,
    queryFn: () => listDocuments(apiClient).then((r) => r.data),
  });
}

export function useDocument(uuid: string | null) {
  return useQuery({
    queryKey: documentKey(uuid ?? ''),
    queryFn: () => getDocument(apiClient, uuid!).then((r) => r.data),
    enabled: !!uuid,
    refetchInterval: (query) => {
      const doc = query.state.data as Document | undefined;
      const status = doc?.latestExtraction?.status;

      if (!status || status === 'pending' || status === 'running') return 3000;
      return false;
    },
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: UploadDocumentInput) => uploadDocument(apiClient, input).then((r) => r.data),
    onSuccess: (doc) => {
      queryClient.setQueryData(documentKey(doc.uuid), doc);
      queryClient.invalidateQueries({ queryKey: DOCUMENTS_KEY });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => deleteDocument(apiClient, uuid),
    onSuccess: (_data, uuid) => {
      queryClient.removeQueries({ queryKey: documentKey(uuid) });
      queryClient.invalidateQueries({ queryKey: DOCUMENTS_KEY });
    },
  });
}
