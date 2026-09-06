import { AxiosInstance } from 'axios';
import { DIRECTORY_ENDPOINTS } from '../constants';
import type { DirectoryToken, PaginatedResponse } from '../types';

export const getDirectoryTokens = (apiClient: AxiosInstance) =>
  apiClient.get<PaginatedResponse<DirectoryToken>>(DIRECTORY_ENDPOINTS.TOKENS.LIST);

export const getDirectoryToken = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<DirectoryToken>(DIRECTORY_ENDPOINTS.TOKENS.DETAIL(uuid));
