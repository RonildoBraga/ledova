/**
 * TanStack Query hooks for the documents API.
 *
 * `useDocument(uuid)` polls every 3 s as long as the extraction is
 * still `pending` or `running`. Once it lands on `succeeded` /
 * `failed` we stop polling — saves bandwidth and avoids hammering
 * the backend.
 */

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
      // No extraction yet, or still running → keep polling.
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
      // Seed the per-doc cache so the polling query starts with the
      // upload response and refreshes from there.
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
      // Drop the per-doc cache to stop any in-flight polling and
      // refresh the list so the card disappears immediately.
      queryClient.removeQueries({ queryKey: documentKey(uuid) });
      queryClient.invalidateQueries({ queryKey: DOCUMENTS_KEY });
    },
  });
}
