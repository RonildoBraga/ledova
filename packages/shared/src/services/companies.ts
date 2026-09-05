import { AxiosInstance } from 'axios';
import { COMPANY_ENDPOINTS } from '../constants';
import type {
  Company,
  CompanyUpdate,
  CompanyStats,
  CompanyRegistration,
  CompanyRegistrationResponse,
  CompanyDocument,
  DocumentUpload,
  ApplicationResponse,
  PaginatedResponse,
} from '../types';

export const getCompanies = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<Company>>(COMPANY_ENDPOINTS.BASE);

export const registerCompany = (apiClient: AxiosInstance, data: CompanyRegistration) =>
  apiClient.post<CompanyRegistrationResponse>(COMPANY_ENDPOINTS.BASE, data);

export const getCompany = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<Company>(COMPANY_ENDPOINTS.DETAIL(uuid));

export const updateCompany = (apiClient: AxiosInstance, uuid: string, data: CompanyUpdate) =>
  apiClient.patch<Company>(COMPANY_ENDPOINTS.DETAIL(uuid), data);

export const getCompanyStats = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<CompanyStats>(COMPANY_ENDPOINTS.STATS(uuid));

export const getCompanyDocuments = (apiClient: AxiosInstance, companyUuid: string) =>
  apiClient.get<PaginatedResponse<CompanyDocument>>(COMPANY_ENDPOINTS.DOCUMENTS(companyUuid));

export const uploadCompanyDocument = (apiClient: AxiosInstance, companyUuid: string, data: DocumentUpload) => {
  const formData = new FormData();
  formData.append('file', data.file);
  formData.append('document_type', data.documentType);
  formData.append('name', data.name);

  return apiClient.post<CompanyDocument>(COMPANY_ENDPOINTS.DOCUMENTS(companyUuid), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const deleteCompanyDocument = (apiClient: AxiosInstance, companyUuid: string, documentUuid: string) =>
  apiClient.delete(COMPANY_ENDPOINTS.DOCUMENT_DETAIL(companyUuid, documentUuid));

export const submitApplication = (apiClient: AxiosInstance, companyUuid: string) =>
  apiClient.post<ApplicationResponse>(COMPANY_ENDPOINTS.SUBMIT(companyUuid), { confirm: true });
