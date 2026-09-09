import { useState, useCallback, useEffect, useRef } from 'react';
import { apiClient } from '../services/apiClient';
import { fetchImportBalances } from '@ledova/shared';
import type { DerivedAddress } from '@ledova/shared';

export function useFetchBalances(userAccountUuid: string | undefined) {
  const [balances, setBalances] = useState<Map<string, string>>(new Map());
  const [isLoadingBalances, setIsLoadingBalances] = useState(false);
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
    setBalances(new Map());
    setIsLoadingBalances(false);
    return () => {
      generation.current += 1;
    };
  }, [userAccountUuid]);

  const fetchBalances = useCallback(
    async (addressList: DerivedAddress[]) => {
      const current = ++generation.current;
      setBalances(new Map());
      setIsLoadingBalances(true);
      const result = await fetchImportBalances(apiClient, addressList, userAccountUuid);
      if (current === generation.current) {
        setBalances(result);
        setIsLoadingBalances(false);
      }
    },
    [userAccountUuid],
  );

  return { balances, isLoadingBalances, fetchBalances };
}
