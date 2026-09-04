import { AxiosInstance } from 'axios';
import { PORTFOLIO_ENDPOINTS } from '@ledova/shared-constants';
import type {
  Portfolio,
  PaginatedResponse,
  PortfolioSnapshot,
  PortfolioSnapshotQueryParams,
} from '@ledova/shared-types';

export const getPortfolios = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<Portfolio>>(PORTFOLIO_ENDPOINTS.BASE);

export const getPortfolioSnapshots = (
  apiClient: AxiosInstance,
  portfolioUuid: string,
  params?: PortfolioSnapshotQueryParams,
) => apiClient.get<PortfolioSnapshot[]>(`${PORTFOLIO_ENDPOINTS.BASE}${portfolioUuid}/snapshots/`, { params });
