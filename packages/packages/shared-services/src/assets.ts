import { AxiosInstance, AxiosResponse } from 'axios';
import type { Asset, AssetQueryParams, PaginatedResponse } from '@ledova/shared-types';
import { ASSET_ENDPOINTS } from '@ledova/shared-constants';
import { getNextPageParam } from '@ledova/shared-utils';

export const getAssets = (apiClient: AxiosInstance, params?: AssetQueryParams) =>
  apiClient.get<PaginatedResponse<Asset>>(ASSET_ENDPOINTS.BASE, { params });

export const getAssetsNextPage = (lastPage: AxiosResponse<PaginatedResponse<Asset>>): number | undefined =>
  getNextPageParam(lastPage.data);

export const getAssetByUuid = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.get<Asset>(`${ASSET_ENDPOINTS.BASE}${uuid}/`);
