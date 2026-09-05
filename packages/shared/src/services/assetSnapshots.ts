import { AxiosInstance } from 'axios';
import type { AssetSnapshot, AssetSnapshotQueryParams } from '../types';
import { ASSET_ENDPOINTS } from '../constants';

export const getAssetSnapshots = async (
  apiClient: AxiosInstance,
  assetUuid: string,
  params?: AssetSnapshotQueryParams,
) => {
  return apiClient.get<AssetSnapshot[]>(`${ASSET_ENDPOINTS.BASE}${assetUuid}/snapshots/`, { params });
};
