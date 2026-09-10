import { AxiosInstance } from 'axios';
import { OFFERING_ENDPOINTS } from '../constants';
import type { IssuerSubscription, Offering, OfferingListItem, OfferingInput, PaginatedResponse } from '../types';

export const getOfferings = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<OfferingListItem>>(OFFERING_ENDPOINTS.BASE);

export const getOffering = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<Offering>(OFFERING_ENDPOINTS.DETAIL(uuid));

export const createOffering = (apiClient: AxiosInstance, data: OfferingInput) =>
  apiClient.post<Offering>(OFFERING_ENDPOINTS.BASE, data);

export const updateOffering = (apiClient: AxiosInstance, uuid: string, data: Partial<OfferingInput>) =>
  apiClient.patch<Offering>(OFFERING_ENDPOINTS.DETAIL(uuid), data);

export const deleteOffering = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.delete(OFFERING_ENDPOINTS.DETAIL(uuid));

export const submitOffering = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.post<Offering>(OFFERING_ENDPOINTS.SUBMIT(uuid), {});

export const getOfferingSubscriptions = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<PaginatedResponse<IssuerSubscription>>(OFFERING_ENDPOINTS.SUBSCRIPTIONS(uuid));

export const withdrawOffering = (apiClient: AxiosInstance, uuid: string, reason: string) =>
  apiClient.post<Offering>(OFFERING_ENDPOINTS.WITHDRAW(uuid), { reason });
