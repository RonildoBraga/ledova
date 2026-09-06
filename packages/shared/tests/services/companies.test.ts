import type { AxiosInstance } from 'axios';
import { COMPANY_ENDPOINTS } from '../../src/constants';
import { getCompanyDocumentFile } from '../../src/services/companies';

describe('company document file service', () => {
  const get = jest.fn();
  const apiClient = { get } as unknown as AxiosInstance;

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('addresses the authenticated streaming route rather than a media path', () => {
    const url = COMPANY_ENDPOINTS.DOCUMENT_FILE('company-uuid', 'document-uuid');

    expect(url).toBe('/api/v1/companies/company-uuid/documents/document-uuid/file/');
    expect(url).not.toContain('/media/');
  });

  it('asks for the bytes so a bearer client can hand them to a viewer', () => {
    getCompanyDocumentFile(apiClient, 'company-uuid', 'document-uuid');

    expect(get).toHaveBeenCalledWith('/api/v1/companies/company-uuid/documents/document-uuid/file/', {
      responseType: 'arraybuffer',
    });
  });
});
