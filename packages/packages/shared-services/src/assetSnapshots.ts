import { AxiosInstance } from 'axios';
import type { AssetSnapshot, AssetSnapshotQueryParams } from '@ledova/shared-types';
import { ASSET_ENDPOINTS } from '@ledova/shared-constants';

export const getAssetSnapshots = async (
  apiClient: AxiosInstance,
  assetUuid: string,
  params?: AssetSnapshotQueryParams,
) => {
  return apiClient.get<AssetSnapshot[]>(`${ASSET_ENDPOINTS.BASE}${assetUuid}/snapshots/`, { params });
};
