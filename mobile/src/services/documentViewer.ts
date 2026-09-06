import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { getCompanyDocumentFile } from '@ledova/shared';
import type { CompanyDocument } from '@ledova/shared';
import { apiClient } from './apiClient';

const EXTENSIONS: Record<string, string> = {
  'application/pdf': '.pdf',
  'image/png': '.png',
  'image/jpeg': '.jpg',
};

const UTIS: Record<string, string> = {
  'application/pdf': 'com.adobe.pdf',
  'image/png': 'public.png',
  'image/jpeg': 'public.jpeg',
};

function cacheFileFor(document: CompanyDocument) {
  return new File(Paths.cache, 'company-documents', `${document.uuid}${EXTENSIONS[document.mimeType] ?? ''}`);
}

export async function openCompanyDocument(companyUuid: string, document: CompanyDocument): Promise<void> {
  if (!(await Sharing.isAvailableAsync())) {
    throw new Error('This device cannot open documents.');
  }

  const { data } = await getCompanyDocumentFile(apiClient, companyUuid, document.uuid);
  const file = cacheFileFor(document);
  if (file.exists) {
    file.delete();
  }
  file.create({ intermediates: true, overwrite: true });
  file.write(new Uint8Array(data));

  await Sharing.shareAsync(file.uri, { mimeType: document.mimeType, UTI: UTIS[document.mimeType] });
}
