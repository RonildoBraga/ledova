import { AxiosInstance } from 'axios';
import { OFFERING_ENDPOINTS } from '../constants';
import type { Offering, OfferingInput, PaginatedResponse } from '../types';

export const getOfferings = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<Offering>>(OFFERING_ENDPOINTS.BASE);

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

export const withdrawOffering = (apiClient: AxiosInstance, uuid: string, reason: string) =>
  apiClient.post<Offering>(OFFERING_ENDPOINTS.WITHDRAW(uuid), { reason });
