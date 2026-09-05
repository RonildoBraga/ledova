import { AxiosInstance } from 'axios';
import { INVESTOR_CLASSIFICATION_ENDPOINTS } from '../constants';
import type {
  InvestorClassification,
  InvestorClassificationSubmission,
  InvestorEligibility,
  PaginatedResponse,
} from '../types';

export const getInvestorClassifications = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<InvestorClassification>>(INVESTOR_CLASSIFICATION_ENDPOINTS.BASE);

export const getInvestorEligibility = (apiClient: AxiosInstance) =>
  apiClient.get<InvestorEligibility>(INVESTOR_CLASSIFICATION_ENDPOINTS.ELIGIBILITY);

export const submitInvestorClassification = (apiClient: AxiosInstance, data: InvestorClassificationSubmission) => {
  const formData = new FormData();
  formData.append('evidence_file', data.file);
  formData.append('user_account', data.userAccount);
  formData.append('category', data.category);
  formData.append('declaration_accepted', 'true');
  formData.append('declared_basis', data.declaredBasis);
  if (data.company) formData.append('company', data.company);
  if (data.certificateIssuedAt) formData.append('certificate_issued_at', data.certificateIssuedAt);
  if (data.certifierName) formData.append('certifier_name', data.certifierName);
  if (data.certifierBody) formData.append('certifier_body', data.certifierBody);
  if (data.certifierMembershipNumber) {
    formData.append('certifier_membership_number', data.certifierMembershipNumber);
  }

  return apiClient.post<InvestorClassification>(INVESTOR_CLASSIFICATION_ENDPOINTS.BASE, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const deleteInvestorClassification = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.delete(INVESTOR_CLASSIFICATION_ENDPOINTS.DETAIL(uuid));
