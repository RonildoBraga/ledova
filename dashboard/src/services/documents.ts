/**
 * Documents API service.
 *
 * Mirrors the wallets.ts pattern from @ledova/shared
 * (taking apiClient explicitly), but lives in the dashboard for the
 * PoC. Lift later if mobile needs the same surface.
 */

import type { AxiosInstance } from 'axios';
import type { Document, DocumentType } from '../types/document';

interface PaginatedDocuments {
  count: number;
  next: string | null;
  previous: string | null;
  results: Document[];
}

export const listDocuments = (apiClient: AxiosInstance) => apiClient.get<PaginatedDocuments>('/api/v1/documents/');

export const getDocument = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<Document>(`/api/v1/documents/${uuid}/`);

export interface UploadDocumentInput {
  file: File;
  documentType: DocumentType;
  note?: string;
}

export const uploadDocument = (apiClient: AxiosInstance, input: UploadDocumentInput) => {
  const form = new FormData();
  form.append('file', input.file);
  form.append('document_type', input.documentType);
  if (input.note) form.append('note', input.note);

  return apiClient.post<Document>('/api/v1/documents/', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const deleteDocument = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.delete(`/api/v1/documents/${uuid}/`);
