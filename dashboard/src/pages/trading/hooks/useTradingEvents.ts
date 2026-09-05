import { useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { TRADING_ENDPOINTS, TRADING_CONFIG, TRADING_EVENT_INVALIDATION_MAP } from '@ledova/shared';

export function useTradingEvents(tokenUuid: string | null | undefined) {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectDelayRef = useRef<number>(TRADING_CONFIG.SSE_RECONNECT_DELAY);

  const connect = useCallback(() => {
    if (!tokenUuid) return;

    eventSourceRef.current?.close();

    const baseUrl = (import.meta.env.VITE_API_URL as string).replace(/\/$/, '');
    const url = `${baseUrl}${TRADING_ENDPOINTS.EVENTS.STREAM}?token=${tokenUuid}`;
    const es = new EventSource(url, { withCredentials: true });

    es.onopen = () => {
      reconnectDelayRef.current = TRADING_CONFIG.SSE_RECONNECT_DELAY;
    };

    for (const [eventType, queryKeys] of Object.entries(TRADING_EVENT_INVALIDATION_MAP)) {
      es.addEventListener(eventType, () => {
        for (const queryKey of queryKeys) {
          queryClient.invalidateQueries({ queryKey });
        }
      });
    }

    es.onerror = () => {
      es.close();
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, TRADING_CONFIG.SSE_MAX_RECONNECT_DELAY);
        connect();
      }, reconnectDelayRef.current);
    };

    eventSourceRef.current = es;
  }, [tokenUuid, queryClient]);

  useEffect(() => {
    connect();

    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);
}
