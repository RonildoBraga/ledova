import { useEffect, useRef } from 'react';
import { AppState } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import EventSource from 'react-native-sse';
import { TRADING_ENDPOINTS, TRADING_CONFIG, TRADING_EVENT_INVALIDATION_MAP } from '@ledova/shared';
import type { TradingEventType } from '@ledova/shared';
import { getAccessToken } from '../../../services/tokenStorage';
import { getTradingEventsUrl } from '../../../config/networkPolicy';

type SSEEventTypes = TradingEventType | 'connected';

export function useTradingEvents(tokenUuid: string | null | undefined) {
  const queryClient = useQueryClient();
  const esRef = useRef<EventSource<SSEEventTypes> | null>(null);
  const reconnectDelayRef = useRef<number>(TRADING_CONFIG.SSE_RECONNECT_DELAY);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    async function connect() {
      if (!tokenUuid) return;

      esRef.current?.close();

      let url: string;
      try {
        url = getTradingEventsUrl(TRADING_ENDPOINTS.EVENTS.STREAM, tokenUuid);
      } catch {
        return;
      }
      const accessToken = await getAccessToken();
      if (!accessToken) return;

      const es = new EventSource<SSEEventTypes>(url, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      es.addEventListener('open', () => {
        reconnectDelayRef.current = TRADING_CONFIG.SSE_RECONNECT_DELAY;
      });

      for (const [eventType, queryKeys] of Object.entries(TRADING_EVENT_INVALIDATION_MAP)) {
        es.addEventListener(eventType as TradingEventType, () => {
          for (const queryKey of queryKeys) {
            queryClient.invalidateQueries({ queryKey });
          }
        });
      }

      es.addEventListener('error', () => {
        es.close();
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, TRADING_CONFIG.SSE_MAX_RECONNECT_DELAY);
          connect();
        }, reconnectDelayRef.current);
      });

      esRef.current = es;
    }

    connect();

    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        esRef.current?.close();
        connect();
      }
    });

    return () => {
      esRef.current?.close();
      esRef.current = null;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      sub.remove();
    };
  }, [tokenUuid, queryClient]);
}
