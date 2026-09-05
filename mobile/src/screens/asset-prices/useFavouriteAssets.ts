import { useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getFavouriteAssets, addFavouriteAsset, removeFavouriteAsset, CACHE_TIMING } from '@ledova/shared';
import type { FavouriteAsset } from '@ledova/shared';
import { apiClient } from '../../services/apiClient';
import { useAuth } from '../../hooks/useAuth';
import { useUserPreferences } from '../../hooks/useUserPreferences';

export function useFavouriteAssets() {
  const { isAuthenticated } = useAuth();
  const { selectedAccount } = useUserPreferences();
  const queryClient = useQueryClient();

  const favouritesQuery = useQuery({
    queryKey: ['favouriteAssets'],
    queryFn: () => getFavouriteAssets(apiClient),
    enabled: isAuthenticated,
    staleTime: CACHE_TIMING.DEFAULT_STALE_TIME,
    gcTime: CACHE_TIMING.EXTRA_LONG_GC_TIME,
  });

  const favourites: FavouriteAsset[] = favouritesQuery.data?.data?.results ?? [];

  const favouriteAssetUuids = useMemo(
    () => new Set<string>(favourites.map((f: FavouriteAsset) => f.asset.uuid)),
    [favourites],
  );

  const assetToFavouriteMap = useMemo(
    () => new Map<string, string>(favourites.map((f: FavouriteAsset) => [f.asset.uuid, f.uuid])),
    [favourites],
  );

  const addMutation = useMutation({
    mutationFn: (assetUuid: string) =>
      addFavouriteAsset(apiClient, { asset: assetUuid, userAccount: selectedAccount!.uuid }),
    onMutate: async (assetUuid) => {
      await queryClient.cancelQueries({ queryKey: ['favouriteAssets'] });

      const previousFavourites = queryClient.getQueryData(['favouriteAssets']);

      return { previousFavourites, assetUuid };
    },
    onError: (_err, _assetUuid, context) => {
      if (context?.previousFavourites) {
        queryClient.setQueryData(['favouriteAssets'], context.previousFavourites);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['favouriteAssets'] });
    },
  });

  const removeMutation = useMutation({
    mutationFn: (favouriteUuid: string) => removeFavouriteAsset(apiClient, favouriteUuid),
    onMutate: async (favouriteUuid) => {
      await queryClient.cancelQueries({ queryKey: ['favouriteAssets'] });

      const previousFavourites = queryClient.getQueryData(['favouriteAssets']);

      queryClient.setQueryData(['favouriteAssets'], (old: typeof favouritesQuery.data) => {
        if (!old?.data?.results) return old;
        return {
          ...old,
          data: {
            ...old.data,
            results: old.data.results.filter((f: FavouriteAsset) => f.uuid !== favouriteUuid),
          },
        };
      });

      return { previousFavourites };
    },
    onError: (_err, _favouriteUuid, context) => {
      if (context?.previousFavourites) {
        queryClient.setQueryData(['favouriteAssets'], context.previousFavourites);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['favouriteAssets'] });
    },
  });

  const isFavourite = useCallback((assetUuid: string) => favouriteAssetUuids.has(assetUuid), [favouriteAssetUuids]);

  const toggleFavourite = useCallback(
    (assetUuid: string) => {
      if (favouriteAssetUuids.has(assetUuid)) {
        const favouriteUuid = assetToFavouriteMap.get(assetUuid);
        if (favouriteUuid) {
          removeMutation.mutate(favouriteUuid);
        }
      } else if (selectedAccount?.uuid) {
        addMutation.mutate(assetUuid);
      }
    },
    [favouriteAssetUuids, assetToFavouriteMap, addMutation, removeMutation, selectedAccount?.uuid],
  );

  return {
    isFavourite,
    toggleFavourite,
  };
}
