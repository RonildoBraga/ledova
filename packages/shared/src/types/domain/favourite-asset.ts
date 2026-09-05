import type { BaseQueryParams } from '../api';
import type { Asset } from './asset';

export interface FavouriteAsset {
  uuid: string;
  userAccount: string;
  asset: Asset;
  createdAt: string;
  updatedAt: string;
}

export interface CreateFavouriteAsset {
  asset: string;
  userAccount: string;
}

export interface FavouriteAssetQueryParams extends BaseQueryParams {
  user_account?: string;
  asset?: string;
}
