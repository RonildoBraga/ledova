import { AxiosInstance } from 'axios';
import { SUBSCRIPTION_ENDPOINTS } from '../constants';
import type { PaginatedResponse, Subscription, SubscriptionDetail, SubscriptionInput } from '../types';

export const getSubscriptions = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<Subscription>>(SUBSCRIPTION_ENDPOINTS.BASE);

export const getSubscription = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<SubscriptionDetail>(SUBSCRIPTION_ENDPOINTS.DETAIL(uuid));

export const createSubscription = (apiClient: AxiosInstance, data: SubscriptionInput) =>
  apiClient.post<SubscriptionDetail>(SUBSCRIPTION_ENDPOINTS.BASE, data);

export const submitSubscription = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.post<SubscriptionDetail>(SUBSCRIPTION_ENDPOINTS.SUBMIT(uuid), {});

export const withdrawSubscription = (apiClient: AxiosInstance, uuid: string, reason: string) =>
  apiClient.post<SubscriptionDetail>(SUBSCRIPTION_ENDPOINTS.WITHDRAW(uuid), { reason });
