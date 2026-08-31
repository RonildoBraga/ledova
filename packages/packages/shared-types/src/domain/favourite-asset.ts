import type { BaseQueryParams } from '../api';
import type { Asset } from './asset';

/**
 * A user's favourite asset - returned with nested Asset data.
 */
export interface FavouriteAsset {
  uuid: string;
  userAccount: string;
  asset: Asset;
  createdAt: string;
  updatedAt: string;
}

/**
 * Request body for creating a favourite asset.
 * Both asset and userAccount UUIDs are required.
 */
export interface CreateFavouriteAsset {
  asset: string;
  userAccount: string;
}

/**
 * Query parameters for favourite asset endpoints.
 *
 * NAMING CONVENTION: Query params use snake_case following REST API URL standards.
 */
export interface FavouriteAssetQueryParams extends BaseQueryParams {
  user_account?: string;
  asset?: string;
}
