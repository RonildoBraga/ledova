import { AxiosInstance, AxiosResponse } from 'axios';
import type {
  CreateFavouriteAsset,
  FavouriteAsset,
  FavouriteAssetQueryParams,
  PaginatedResponse,
} from '@ledova/shared-types';
import { FAVOURITE_ASSET_ENDPOINTS } from '@ledova/shared-constants';
import { getNextPageParam } from '@ledova/shared-utils';

export const getFavouriteAssets = (apiClient: AxiosInstance, params?: FavouriteAssetQueryParams) =>
  apiClient.get<PaginatedResponse<FavouriteAsset>>(FAVOURITE_ASSET_ENDPOINTS.BASE, { params });

export const getFavouriteAssetsNextPage = (
  lastPage: AxiosResponse<PaginatedResponse<FavouriteAsset>>,
): number | undefined => getNextPageParam(lastPage.data);

export const addFavouriteAsset = (apiClient: AxiosInstance, data: CreateFavouriteAsset) =>
  apiClient.post<FavouriteAsset>(FAVOURITE_ASSET_ENDPOINTS.BASE, data);

export const removeFavouriteAsset = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.delete(FAVOURITE_ASSET_ENDPOINTS.DETAIL(uuid));
