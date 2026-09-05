import { AxiosInstance } from 'axios';
import type { CreateFavouriteAsset, FavouriteAsset, FavouriteAssetQueryParams, PaginatedResponse } from '../types';
import { FAVOURITE_ASSET_ENDPOINTS } from '../constants';

export const getFavouriteAssets = (apiClient: AxiosInstance, params?: FavouriteAssetQueryParams) =>
  apiClient.get<PaginatedResponse<FavouriteAsset>>(FAVOURITE_ASSET_ENDPOINTS.BASE, { params });

export const addFavouriteAsset = (apiClient: AxiosInstance, data: CreateFavouriteAsset) =>
  apiClient.post<FavouriteAsset>(FAVOURITE_ASSET_ENDPOINTS.BASE, data);

export const removeFavouriteAsset = (apiClient: AxiosInstance, uuid: string) =>
  apiClient.delete(FAVOURITE_ASSET_ENDPOINTS.DETAIL(uuid));
