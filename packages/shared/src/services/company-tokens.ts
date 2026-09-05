import { AxiosInstance } from 'axios';
import { COMPANY_TOKEN_ENDPOINTS } from '../constants';
import type {
  CompanyShareToken,
  TokenCreate,
  TokenHoldersResponse,
  TokenIssuancesResponse,
  CapitalIncreaseCreate,
  CapitalIncreaseRequest,
  CapitalIncreaseResponse,
  PaginatedResponse,
} from '../types';

export const getCompanyTokens = (
  apiClient: AxiosInstance,
  params?: { page?: number; page_size?: number; status?: string },
) => apiClient.get<PaginatedResponse<CompanyShareToken>>(COMPANY_TOKEN_ENDPOINTS.BASE, { params });

export const getCompanyToken = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<CompanyShareToken>(COMPANY_TOKEN_ENDPOINTS.DETAIL(uuid));

export const createCompanyToken = (apiClient: AxiosInstance, data: TokenCreate) =>
  apiClient.post<CompanyShareToken>(COMPANY_TOKEN_ENDPOINTS.BASE, data);

export const deployCompanyToken = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.post<CompanyShareToken>(COMPANY_TOKEN_ENDPOINTS.DEPLOY(uuid));

export const pauseCompanyToken = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.post<CompanyShareToken>(COMPANY_TOKEN_ENDPOINTS.PAUSE(uuid));

export const unpauseCompanyToken = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.post<CompanyShareToken>(COMPANY_TOKEN_ENDPOINTS.UNPAUSE(uuid));

export const getCompanyTokenHolders = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<TokenHoldersResponse>(COMPANY_TOKEN_ENDPOINTS.HOLDERS(uuid));

export const getCompanyTokenIssuances = (
  apiClient: AxiosInstance,
  uuid: string,
  params?: { page?: number; page_size?: number; status?: string },
) => apiClient.get<TokenIssuancesResponse>(COMPANY_TOKEN_ENDPOINTS.ISSUANCES(uuid), { params });

export const issueCompanyShares = (
  apiClient: AxiosInstance,
  tokenUuid: string,
  data: { recipient: string; amount: number; reason?: string },
) => apiClient.post<CompanyShareToken>(COMPANY_TOKEN_ENDPOINTS.ISSUE(tokenUuid), data);

export const getCapitalIncreases = (
  apiClient: AxiosInstance,
  params?: { token?: string; status?: string; page?: number; page_size?: number },
) => apiClient.get<CapitalIncreaseResponse>(COMPANY_TOKEN_ENDPOINTS.CAPITAL_INCREASES, { params });

export const createCapitalIncrease = (apiClient: AxiosInstance, data: CapitalIncreaseCreate) =>
  apiClient.post<CapitalIncreaseRequest>(COMPANY_TOKEN_ENDPOINTS.CAPITAL_INCREASES, data);

export const submitCapitalIncrease = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.post<{ message: string; request: CapitalIncreaseRequest }>(
    COMPANY_TOKEN_ENDPOINTS.CAPITAL_INCREASE_SUBMIT(uuid),
  );
