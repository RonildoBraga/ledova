import { AxiosInstance } from 'axios';
import { PORTFOLIO_ENDPOINTS } from '@ledova/shared-constants';
import type {
  Portfolio,
  CreatePortfolio,
  UpdatePortfolio,
  PaginatedResponse,
  PortfolioSnapshot,
  PortfolioSnapshotQueryParams,
} from '@ledova/shared-types';

type PaginatedPortfolios = PaginatedResponse<Portfolio>;

export const getPortfolios = (apiClient: AxiosInstance) => {
  return apiClient.get<PaginatedPortfolios>(PORTFOLIO_ENDPOINTS.BASE);
};

export const createPortfolio = (apiClient: AxiosInstance, data: CreatePortfolio) => {
  return apiClient.post<Portfolio>(PORTFOLIO_ENDPOINTS.BASE, data);
};

export const updatePortfolio = (apiClient: AxiosInstance, uuid: string, data: UpdatePortfolio) => {
  return apiClient.patch<Portfolio>(`${PORTFOLIO_ENDPOINTS.BASE}${uuid}/`, data);
};

export const deletePortfolio = (apiClient: AxiosInstance, uuid: string) => {
  return apiClient.delete(`${PORTFOLIO_ENDPOINTS.BASE}${uuid}/`);
};

export const getPortfolioByUuid = (apiClient: AxiosInstance, uuid: string) => {
  return apiClient.get<Portfolio>(`${PORTFOLIO_ENDPOINTS.BASE}${uuid}/`);
};

export const getPortfolioSnapshots = (
  apiClient: AxiosInstance,
  portfolioUuid: string,
  params?: PortfolioSnapshotQueryParams,
) => apiClient.get<PortfolioSnapshot[]>(`${PORTFOLIO_ENDPOINTS.BASE}${portfolioUuid}/snapshots/`, { params });

export const addWalletToPortfolio = (apiClient: AxiosInstance, portfolioUuid: string, walletUuid: string) =>
  apiClient.post<Portfolio>(`${PORTFOLIO_ENDPOINTS.BASE}${portfolioUuid}/add-wallet/`, {
    walletUuid,
  });

export const removeWalletFromPortfolio = (apiClient: AxiosInstance, portfolioUuid: string, walletUuid: string) =>
  apiClient.post<Portfolio>(`${PORTFOLIO_ENDPOINTS.BASE}${portfolioUuid}/remove-wallet/`, {
    walletUuid,
  });
