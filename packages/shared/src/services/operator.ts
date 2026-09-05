import { AxiosInstance } from 'axios';
import { OPERATOR_ENDPOINTS } from '../constants';
import type { Operator } from '../types';

export const getOperator = (apiClient: AxiosInstance) => apiClient.get<Operator>(OPERATOR_ENDPOINTS.BASE);
